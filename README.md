# AWS DynDNS

## Create AWS user

*Note:* This only needs to be done once per AWS account.

We need a user that has access to change DNS records. We create a user that
has access to do that, and nothing else.

```shell
$ aws --profile test --region eu-central-1 cloudformation create-stack --stack-name rl-dyndnsuser --template-url https://s3.eu-central-1.amazonaws.com/templates.bitbit/standard/dyndns_user.yaml --capabilities CAPABILITY_IAM
{
    "StackId": "arn:aws:cloudformation:eu-central-1:012345678901:stack/dyndnsuser/57ca1e17-e53c-41d8-9732-494293971918"
}
```
Check that the stack is done creating the resource
```shell
$ aws --profile test --region eu-central-1 cloudformation describe-stacks --stack-name dyndnsuser --query Stacks[].StackStatus --output text
CREATE_COMPLETE
```
Then we create access key to that user

```shell
$ USERNAME=$(aws --profile test --region eu-central-1 cloudformation describe-stacks --stack-name dyndnsuser --query Stacks[].Outputs[].OutputValue --output text)
$ aws --profile test iam create-access-key --user-name $USERNAME --query AccessKey.[AccessKeyId,SecretAccessKey] --output text | awk '{print "aws_access_key_id =  " $1 "\naws_secret_access_key = " $2}'
aws_access_key_id =  AKIAQGZOMFGZOMFGRRUI
aws_secret_access_key = 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
```

Note the access key and the secret access key, you need them later.

## Create config

We can retrive the zone info like this.
```shell
$ aws --profile test route53 list-hosted-zones --query HostedZones[].[Id,Name,Config.PrivateZone]  --output text | sed s%/hostedzone/%% | awk '/False$/ {print "  - ZoneId: " $1 "\n    Domain: "$2} '
  - ZoneId: ZOMGSIZOMG1GI3
    Domain: my.example.com.
```

Then we combine the config to be:

```yaml
access_keys:
  test:
    aws_access_key_id: AKIAQGZOMFGZOMFGRRUI
    aws_secret_access_key: DU+zomgOMGzomfgzOHbkqeYd0594yUiGBXj9mGuz
zones:
  - test:
      ZoneId: ZOMGSIZOMG1GI3
      Domain: my.example.com.
```

Note the trailing dot in the domain name, leave it there.

Store that file in `/usr/local/etc/aws_dyndns.yaml`


## Use the script

Set an A record
```
$ aws_dyndns.py update dyndns.my.example.com a 127.0.0.4
```

Add a value to the A record

```
$ aws_dyndns.py add dyndns.my.example.com a 127.0.0.5
```
