# running the first time
Confirm you have the core files, including a filled-out .env and all of the files in the src folder:
- Dockerfile
- docker-compose.yml
- rust-toolchain
- Cargo.lock
- Cargo.toml
- .env
- ./src/

Confirm you have enough storage, should have a minimum of ~12GB. You can free up space by:
```bash
# Check what's using space in Docker
docker system df -v

# Remove unused images
docker image prune -a -f

# Check space again
df -h
```

Confirm inbound rules via the security group allows for traffic coming in from port 4000. This is done via the AWS UI (prod, US-East-2):
EC2 --> Intances --> nexeo-static --> Security --> click the security groups link --> Edit inbound rules --> Type: Custom TCP / Port: 4000 / Source: 0.0.0.0/0

Build and run the image:
``` bash
docker-compose build
```
The above command can take up to 15-20 minutes to finish, specifically when on the `cargo install` and `libtorch` steps. After, run:

``` bash
docker-compose up -d
```

After pulling the image up in detached (`-d`) mode, view logs with:
```bash
docker-compose logs -f
```

Or, to simply recreate / refresh all in one command (will take longer):
```bash
# Stop and remove all containers
docker-compose down --remove-orphans

# Clean up Docker system
docker system prune -a -f

# Rebuild and start fresh
docker-compose build --no-cache nexeo-sts
docker-compose up -d

docker-compose logs -f
```

In the logs, you'll see a 'start up took ...' message which sigifies that we're ready to take orders:
```
nexeo-sts    | [2025-10-14T10:06:32Z INFO  nexeo_sts::query] Added 46554 out of 46554 modifiers to the vector database.
nexeo-sts    | [2025-10-14T10:06:32Z INFO  nexeo_sts] [4/4]  Query system initialized
nexeo-sts    | [2025-10-14T10:06:32Z INFO  nexeo_sts] Start up took 681.352823061s seconds.
```

# other important commands

## ssh into instance
ssh -o IdentitiesOnly=yes -i "nexeo.pem" ubuntu@ec2-3-134-46-103.us-east-2.compute.amazonaws.com

## generate a QU JWT
QU_JWT=$(curl -sS -X POST 'https://gateway-api.qubeyond.com/api/v4/authentication/oauth2/access-token' \
  -F 'grant_type=client_credentials' \
  -F 'client_id=deepgramjitb405' \
  -F 'client_secret=6Nffn0*5QshgFVT]5>6Y' \
  -F 'scope=menu:*' | jq -r '.access_token')

## pull the mneu
curl -sS -G "https://gateway-api.qubeyond.com/api/v4/sales/menus" -H "Authorization: Bearer $QU_JWT" -H "X-Integration: 682c4b47f7e426d4b8208962" --data-urlencode "LocationId=6743" --data-urlencode "FulfillmentMethod=1" > menu.json