terraform {
  backend "s3" {
    bucket         = "agencyops-terraform-state"
    key            = "z230/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "agencyops-terraform-locks"
    encrypt        = true
  }
}
