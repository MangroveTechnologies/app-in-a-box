output "service_url" {
  value = google_cloud_run_v2_service.app.uri
}

output "artifact_registry_repo" {
  value = google_artifact_registry_repository.repo.name
}
