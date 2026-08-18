terraform {
  backend "s3" {
    key          = "job-board/personal/terraform.tfstate"
    region       = "ap-southeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
