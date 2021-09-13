#!/usr/bin/python3

#  Copyright (C) 2021 Jónas Pálsson
#
#  This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along with this program. If not, see http://www.gnu.org/licenses/.

import dns.resolver
import boto3
import yaml
import argparse
import re
import time
import sys


def getArgs():
  Args = argparse.ArgumentParser(usage='%(prog)s [-v] [-h]] [-t TTL] {add|delete|update} {Name} [IN] {Type} {Target}', description='Add, Delete, Replace DNS records using DDNS.')

  # -v - Verbose?
  Args.add_argument('-v', '--verbose', dest='Verbose', action='store_true',
                    help='Print the rcode returned with for each update')

  # -t - The TTL
  Args.add_argument('-t', dest='TimeToLive', required=False, default="600",
                    help='Specify the TTL. Optional, if not provided TTL will be default to 600.')

  # myInput is a list of additional values required. Actual data varies based on action
  Args.add_argument('myInput', action='store', nargs='+', metavar='add|delete|update',
                    help='{hostname} [IN] {Type} {Target}.')

  myArgs = Args.parse_args()
  return myArgs

def isValidTTL(TTL):
  """
  Valdate the TTL parameter
  """
  try:
    TTL = dns.ttl.from_text(TTL)
  except:
    exit( 'TTL:', TTL, 'is not valid')
  return TTL

def isValidV4Addr(Address):
  """
  Validate a IPv4 address
  """
  try:
    dns.ipv4.inet_aton(Address)
  except:
    exit('Error:', Address, 'is not a valid IPv4 address')
  return True

def isValidV6Addr(Address):
  """
  Validate a IPv4 address
  """
  try:
    dns.ipv6.inet_aton(Address)
  except:
    exit('Error:', Address, 'is not a valid IPv6 address')
  return True

def isValidName(Name):
  """
  Validate a hostname
  """
  if re.match(r'^(\*\.)?(([a-zA-Z0-9]|[a-zA-Z0-9\_][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z]|[A-Za-z][A-Za-z0-9\-]*[A-Za-z0-9]\.?)$', Name):
    return True
  else:
    exit('Error:', Name, 'is not a valid name')


def find_root_domain(domain_name):
  """
  Find the root domain of the domain name given.
  """
  try:
    dnsen = str(dns.resolver.zone_for_name(domain_name))
  except:
    print(sys.exc_info()[1])
    exit()
  return(dnsen)

def find_zone_id(aws_info, dnsen, verbose):
  """
  Find the ZoneID in the configuration file, croak if we do not find it. Fetching corresponding credentials
  """
  if verbose:
    print("Searching for zone id for domain %s" % dnsen)
  zoneid = None
  aws_profile = None
  for profile in aws_info["zones"]:
    for i in range(len(aws_info["zones"][profile])):
      if aws_info["zones"][profile][i]["Domain"] == dnsen:
        zoneid = aws_info["zones"][profile][i]["ZoneId"]
        aws_profile = profile
        if verbose:
          print("Found zone id %s in profile %s" % (dnsen, profile))
  if zoneid == None:
    exit("Did not find zoneid for %s" % dnsen)

  aws_access_key_id = aws_info["access_keys"][aws_profile]["aws_access_key_id"]
  aws_secret_access_key = aws_info["access_keys"][aws_profile]["aws_secret_access_key"]
  return(zoneid,aws_access_key_id,aws_secret_access_key)

def verifymyInput(aws_info, myInput, verbose):
  """
  Validation according to type
  """
  action = myInput[0].lower()
  if action != 'add' and action != 'delete' and action != 'del' and action != 'update':
    print( 'FATAL: Invalid action')
    print( 'Usage: aws_dyndns.py [-t ttl] {add|delete|update} [Name] [Type] [Address]')
    exit()

    type = myInput[2].upper()
    # Based on the type of record we're trying to update we'll run some tests
    if type == 'A' or type == 'AAAA':
      if len(myInput) < 4:
        print('FATAL: not enough options for an A record')
        print('Usage: dyndns.py [-t ttl] {add|delete|update} Name A Address')
        exit()
      isValidName(myInput[1])
      if type == 'A':
        isValidV4Addr(myInput[3])
      elif type == 'AAAA':
        isValidV6Addr(myInput[3])
    if type == 'CNAME' or type == 'NS':
        if len(myInput) < 4:
            print( 'FATAL: not enough options for a CNAME record')
            print( 'Usage: dyndns.py [-t ttl] {add|delete|update} Name CNAME Target')
            exit()
        isValidName(myInput[1])
        isValidName(myInput[3])


  aws_data = find_zone_id(aws_info, find_root_domain(myInput[1]), verbose)
  return(aws_data)

def aws_get_client( aws_data ):
  """
  Normal AWS connection
  """
  session = boto3.Session( aws_access_key_id = aws_data[1],
                           aws_secret_access_key = aws_data[2])
  return session.client( 'route53')


def aws_r53_changes( client,
                     zone_id,
                     action,
                     ttl,
                     verbose ):
  """
  Do the actual changes
  """
  if action[0] == "add":
    (aws_changes, rec) = aws_check_existing( client, action, zone_id)
  elif action[0] == "delete" or action[0] == "del":
    aws_changes = "DELETE"
    rec = [{'Value': action[3]}]
  else:
    aws_changes = "UPSERT"
    rec = [{'Value': action[3]}]

  try:
    response = client.change_resource_record_sets(
      HostedZoneId = zone_id,
      ChangeBatch = {
        'Changes':[
          {
            'Action': aws_changes,
            'ResourceRecordSet': {
              'Name': action[1],
              'Type': action[2].upper(),
              'TTL': int(ttl),
              'ResourceRecords': rec
            }
          }
        ]
      }
    )
    if verbose:
      aws_check_result(client,
                       response)
  except:
    print(sys.exc_info()[1])
    exit()

def aws_check_existing( client, action_array, zone_id):
  """
  If action is "add", we need to check if there exists a value, if it is the same, and if we should append to the values
  """
  paginator = client.get_paginator('list_resource_record_sets')
  results = paginator.paginate(HostedZoneId=zone_id)
  for record_set in results:
    for record in record_set['ResourceRecordSets']:
      if (record['Type'] == action_array[2].upper() and record['Name'] == action_array[1] + '.'):
        for rec in record['ResourceRecords']:
          if action_array[3] + '.' in rec.values():
            print( action_array[1] + " allready has " + action_array[2].upper() + " pointing to " + action_array[3])
            exit(0)
          record['ResourceRecords'].append({'Value': action_array[3]})
          return("UPSERT", record['ResourceRecords'])
  return("CREATE", [{"Value": action_array[3]}])

def aws_check_result( client,
                      response):
  """
  The change_resource_record_sets() function returns immediately, without the changes synced out. This functions exits when changes are no longer "pending"
  """
  new_response = client.get_change( Id = response['ChangeInfo']['Id'] )
  print("Status is: %s" % new_response['ChangeInfo']['Status'])
  if new_response['ChangeInfo']['Status'] == "PENDING":
    time.sleep(2)
    aws_check_result(client,
                     new_response)


def main():
  """
  Main
  """
  with open('/usr/local/etc/aws_dyndns.yaml', 'r') as file:
    aws_dyndns_data = yaml.safe_load(file)
  myArgs = getArgs()

  aws_info = verifymyInput(aws_dyndns_data, myArgs.myInput, myArgs.Verbose)
  isValidTTL(myArgs.TimeToLive)
  session_client = aws_get_client(aws_info)
  aws_r53_changes( session_client, aws_info[0], myArgs.myInput, myArgs.TimeToLive, myArgs.Verbose)




main()
