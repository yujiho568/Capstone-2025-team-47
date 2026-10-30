resource "aws_ecr_repository" "pipeline" {
  name                 = "${var.ecr_repo_name}${var.name_suffix}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}
