import io
import json
import logging
import oci
import datetime
from fdk import response

# --- OCI Authentication and Clients ---
# Replace with your Compartment ID and other details
COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaaqufgrkgzr4zb3dsu53b736mdlgixu33p7jx7yckglghxppfrui6a" ##YOUR_COMPARTMENT_OCID
LOW_CPU_THRESHOLD = 5  #Low CPU Utilization Threshold Value(Percentage)
TIME_WINDOW_MINUTES = 1440  # Check CPU over the last 24 hours

def handler(ctx, data: io.BytesIO = None):
    # Initialize OCI clients
    signer = oci.auth.signers.get_resource_principals_signer()  # If running in OCI Functions
    monitoring_client = oci.monitoring.MonitoringClient(config={}, signer=signer)
    compute_client = oci.core.ComputeClient(config={}, signer=signer)

    # --- Get Instance Metrics ---
    query_metrics_response = monitoring_client.summarize_metrics_data(
        oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace="oci_computeagent",
            query=f"CpuUtilization[1440m].mean()", # CPU Utilization metric over 1440 minutes, averaged
            start_time=(datetime.datetime.now() - datetime.timedelta(minutes=TIME_WINDOW_MINUTES)).isoformat() + "Z",
            end_time=datetime.datetime.now().isoformat() + "Z",
            resource_group="compute",
            compartment_id=COMPARTMENT_ID,
            dimensions={"resourceId": "instance_ocid"} # Need to iterate for each instance later
        )
    )

    # --- Process Metrics and Stop Instances ---
    for metric_data in query_metrics_response.data:
        instance_id = metric_data.dimensions["resourceId"]
        cpu_utilization = metric_data.aggregated_datapoints[0].value  # Get the average CPU

        if cpu_utilization < LOW_CPU_THRESHOLD:
            # Stop the instance
            compute_client.instance_action(
                instance_id=instance_id,
                action="SOFTSTOP"  # Or "STOP" for immediate power off
            )
            print(f"Stopped instance {instance_id} due to low CPU utilization ({cpu_utilization}%)")

    return "Successfully processed instances for low CPU utilization."
