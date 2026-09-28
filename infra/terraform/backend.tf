terraform {
  backend "s3" {
    bucket       = "andre-airmax-terraform-state"
    key          = "airmax.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}
