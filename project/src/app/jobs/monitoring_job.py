from dagster import job
from app import operations


@job(
    config={
        "ops": {
            "connect_to_gcp": {
                "config": {
                    "servers": [
                        "cpl-ssff-adqbbva-dev-16052025",
                        "cpl-ssff-adqbbva-qa-13052025",
                        "cpl-ssff-prepers-dev-11072025",
                        "cpl-ssff-prepers-qa-22072025",
                        "cpl-omni-cpay-dev-21052026",
                        "cpl-omni-cpay-qa-25052026",
                        "cpl-rt-carteras-dev-02082024",
                        "cpl-ssff-corresp-dev-11032026",
                        "cpl-corp-abono-dev-24102025",
                        "cpl-corp-abono-qa-24102025",
                        "cpl-corp-abono-stg-27102025"
                    ]
                }
            }
        }
    }
)
def server_monitoring():
    # 1. Bajar los reportes Excel existentes desde Google Drive
    drive_complete  = operations.download_reports_from_drive()
    connected_info  = operations.connect_to_gcp(start_after=drive_complete)
    nodes_data      = operations.fetch_node_metrics(connected_info)
    pods_data       = operations.fetch_pods_metrics(connected_info)
    generated_files = operations.process_and_report(nodes_data, pods_data)
    operations.upload_reports_to_drive(generated_files)