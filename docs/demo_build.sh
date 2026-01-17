env AWS_PROFILE=changeme bash -lc '
set -euo pipefail

KEEP_TAG_KEY="bloodhound:keep"
KEEP_TAG_VALUE="true"

REGIONS=(us-east-1 us-east-2 us-west-1 us-west-2)
TS="$(date +%Y%m%d%H%M%S)"

say() { echo "[$(date +%H:%M:%S)] $*"; }

get_default_vpc_id() {
  local region="$1"
  aws --region "$region" ec2 describe-vpcs \
    --filters Name=isDefault,Values=true \
    --query "Vpcs[0].VpcId" --output text
}

get_default_sg_id() {
  local region="$1" vpc_id="$2"
  aws --region "$region" ec2 describe-security-groups \
    --filters Name=vpc-id,Values="$vpc_id" Name=group-name,Values=default \
    --query "SecurityGroups[0].GroupId" --output text
}

get_default_subnets() {
  local region="$1" vpc_id="$2"
  aws --region "$region" ec2 describe-subnets \
    --filters Name=vpc-id,Values="$vpc_id" Name=default-for-az,Values=true \
    --query "Subnets[].SubnetId" --output text
}

get_al2023_ami() {
  local region="$1"
  aws --region "$region" ssm get-parameter \
    --name "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64" \
    --query "Parameter.Value" --output text
}

create_ec2() {
  local region="$1" subnet_id="$2" sg_id="$3" ami_id="$4" keep="$5" name="$6"
  local tag_spec

  if [[ "$keep" == "true" ]]; then
    tag_spec="ResourceType=instance,Tags=[{Key=Name,Value=${name}},{Key=${KEEP_TAG_KEY},Value=${KEEP_TAG_VALUE}},{Key=bloodhound:demo,Value=true},{Key=bloodhound:created_by,Value=cursor}]"
  else
    tag_spec="ResourceType=instance,Tags=[{Key=Name,Value=${name}},{Key=bloodhound:demo,Value=true},{Key=bloodhound:created_by,Value=cursor}]"
  fi

  local vol_tag_spec="ResourceType=volume,Tags=[{Key=Name,Value=${name}-root},{Key=bloodhound:demo,Value=true},{Key=bloodhound:created_by,Value=cursor}]"

  aws --region "$region" ec2 run-instances \
    --image-id "$ami_id" \
    --instance-type "t3.micro" \
    --subnet-id "$subnet_id" \
    --security-group-ids "$sg_id" \
    --count 1 \
    --tag-specifications "$tag_spec" "$vol_tag_spec" \
    --query "Instances[0].InstanceId" --output text
}

ensure_rds_subnet_group() {
  local region="$1" name="$2" subnet_ids_csv="$3"

  if aws --region "$region" rds describe-db-subnet-groups --db-subnet-group-name "$name" >/dev/null 2>&1; then
    return 0
  fi

  # shellcheck disable=SC2206
  local subnet_ids=(${subnet_ids_csv})
  if [[ ${#subnet_ids[@]} -lt 2 ]]; then
    echo "ERROR: Need at least 2 default subnets for RDS subnet group in region=${region}, got: ${subnet_ids_csv}" >&2
    return 1
  fi

  aws --region "$region" rds create-db-subnet-group \
    --db-subnet-group-name "$name" \
    --db-subnet-group-description "Bloodhound demo subnet group (${region})" \
    --subnet-ids "${subnet_ids[0]}" "${subnet_ids[1]}" \
    --tags Key=bloodhound:demo,Value=true Key=bloodhound:created_by,Value=cursor >/dev/null
}

create_rds() {
  local region="$1" subnet_group="$2" sg_id="$3" keep="$4" identifier="$5"

  local username="bloodhound"
  local password
  password="$(openssl rand -base64 24 | tr -d '\''/@" '\'' | cut -c1-20)"

  local tags=(Key=bloodhound:demo,Value=true Key=bloodhound:created_by,Value=cursor)
  if [[ "$keep" == "true" ]]; then
    tags+=(Key="${KEEP_TAG_KEY}",Value="${KEEP_TAG_VALUE}")
    tags+=(Key=Name,Value="${identifier}")
  else
    tags+=(Key=Name,Value="${identifier}")
  fi

  aws --region "$region" rds create-db-instance \
    --db-instance-identifier "$identifier" \
    --engine postgres \
    --db-instance-class db.t3.micro \
    --allocated-storage 20 \
    --master-username "$username" \
    --master-user-password "$password" \
    --no-publicly-accessible \
    --backup-retention-period 1 \
    --storage-type gp2 \
    --db-subnet-group-name "$subnet_group" \
    --vpc-security-group-ids "$sg_id" \
    --tags "${tags[@]}" \
    --query "DBInstance.DBInstanceIdentifier" --output text
}

say "Confirming caller identity (profile=geekstar)"
aws sts get-caller-identity --output json

say "Creating EC2 instances (2 per region: 1 whitelisted, 1 not)"
for region in "${REGIONS[@]}"; do
  say "Region: ${region}"

  vpc_id="$(get_default_vpc_id "$region")"
  if [[ -z "$vpc_id" || "$vpc_id" == "None" ]]; then
    echo "ERROR: No default VPC found in region=${region}" >&2
    exit 1
  fi

  sg_id="$(get_default_sg_id "$region" "$vpc_id")"
  subnets="$(get_default_subnets "$region" "$vpc_id")"
  # pick the first subnet for EC2 placement
  subnet_id="$(awk "{print \$1}" <<<"$subnets")"

  ami_id="$(get_al2023_ami "$region")"

  keep_name="bloodhound-demo-ec2-keep-${region}-${TS}"
  nokeep_name="bloodhound-demo-ec2-nokeep-${region}-${TS}"

  keep_id="$(create_ec2 "$region" "$subnet_id" "$sg_id" "$ami_id" true "$keep_name")"
  say "  EC2 (kept)     ${keep_id}  name=${keep_name}"

  nokeep_id="$(create_ec2 "$region" "$subnet_id" "$sg_id" "$ami_id" false "$nokeep_name")"
  say "  EC2 (not kept) ${nokeep_id}  name=${nokeep_name}"
done

say "Creating 2 RDS instances (one kept, one not)"
RDS_KEEP_REGION="us-east-1"
RDS_NOKEEP_REGION="us-west-2"

for region in "$RDS_KEEP_REGION" "$RDS_NOKEEP_REGION"; do
  say "RDS Region: ${region}"
  vpc_id="$(get_default_vpc_id "$region")"
  sg_id="$(get_default_sg_id "$region" "$vpc_id")"
  subnets="$(get_default_subnets "$region" "$vpc_id")"

  subnet_group="bloodhound-demo-subnetgrp-${region}"
  ensure_rds_subnet_group "$region" "$subnet_group" "$subnets"

done

keep_rds_id="bloodhound-demo-rds-keep-${TS}"
nokeep_rds_id="bloodhound-demo-rds-nokeep-${TS}"

vpc_id="$(get_default_vpc_id "$RDS_KEEP_REGION")"
sg_id="$(get_default_sg_id "$RDS_KEEP_REGION" "$vpc_id")"
subnet_group="bloodhound-demo-subnetgrp-${RDS_KEEP_REGION}"
created_keep_rds="$(create_rds "$RDS_KEEP_REGION" "$subnet_group" "$sg_id" true "$keep_rds_id")"
say "  RDS (kept)     ${created_keep_rds}  region=${RDS_KEEP_REGION}"

vpc_id="$(get_default_vpc_id "$RDS_NOKEEP_REGION")"
sg_id="$(get_default_sg_id "$RDS_NOKEEP_REGION" "$vpc_id")"
subnet_group="bloodhound-demo-subnetgrp-${RDS_NOKEEP_REGION}"
created_nokeep_rds="$(create_rds "$RDS_NOKEEP_REGION" "$subnet_group" "$sg_id" false "$nokeep_rds_id")"
say "  RDS (not kept) ${created_nokeep_rds}  region=${RDS_NOKEEP_REGION}"

say "Done. (RDS will take several minutes to become available.)"
'