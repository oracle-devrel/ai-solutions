resource "oci_objectstorage_bucket" "speech_bucket" {
  compartment_id        = var.compartment_id
  namespace             = data.oci_objectstorage_namespace.this.namespace
  name                  = local.effective_speech_bucket_name
  storage_tier          = "Standard"
  versioning            = "Disabled"
  auto_tiering          = "Disabled"
  object_events_enabled = false
}
