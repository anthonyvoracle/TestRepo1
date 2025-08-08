import io
import json
import logging
import oci
from datetime import datetime,timezone
from fdk import response

# --- OCI Authentication and Clients ---
# Replace with your Compartment ID and other details
COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaaqufgrkgzr4zb3dsu53b736mdlgixu33p7jx7yckglghxppfrui6a" ##YOUR_COMPARTMENT_OCID
NOTIFICATION_TOPIC_OCID = "<YOUR_NOTIFICATION_TOPIC_OCID>"  # <-- Set your OCI Notification Topic OCID here
LOW_CPU_THRESHOLD = 5  #Low CPU Utilization Threshold Value(Percentage)
TIME_WINDOW_MINUTES = 1440  # Check CPU over the last 24 hours

def handler(ctx, data: io.BytesIO = None):
    signer = oci.auth.signers.get_resource_principals_signer()
    monitoring_client = oci.monitoring.MonitoringClient(config={}, signer=signer)
    compute_client = oci.core.ComputeClient(config={}, signer=signer)
    ons_client = oci.ons.NotificationDataPlaneClient(config={}, signer=signer)

    # Get all running instances in the compartment
    instances = compute_client.list_instances(
        compartment_id=COMPARTMENT_ID,
        lifecycle_state="RUNNING"
    ).data

    stopped_instances = []

    for instance in instances:
        instance_id = instance.id
        # Query Metrics
        start_time = datetime.now(timezone.utc) - datetime.timedelta(minutes=TIME_WINDOW_MINUTES).isoformat("T") + "Z"
        end_time = datetime.now(timezone.utc).isoformat("T") + "Z"
        metrics_query = oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace="oci_computeagent",
            query="CpuUtilization[1440m].mean()",
            start_time=start_time,
            end_time=end_time,
            resource_group="compute",
            compartment_id=COMPARTMENT_ID,
            dimensions={"resourceId": instance_id}
        )
        response = monitoring_client.summarize_metrics_data(metrics_query)
        data = response.data

        if not data or not data[0].aggregated_datapoints:
            print(f"No CPU metric data for {instance_id}")
            continue

        cpu_mean = data[0].aggregated_datapoints[0].value
        if cpu_mean < LOW_CPU_THRESHOLD:
            compute_client.instance_action(
                instance_id=instance_id,
                action="SOFTSTOP"
            )
            print(f"Stopped instance {instance_id} (average CPU: {cpu_mean:.2f}%)")
            stopped_instances.append(instance_id)
        else:
            print(f"Instance {instance_id} not stopped (average CPU: {cpu_mean:.2f}%)")

 # --- Send OCI Notification if any instances stopped ---
    if stopped_instances:
        subject = "OCI Instances Soft Stopped Due to Low CPU Utilization"
        instances_details = "\n".join(
            [f"- {inst['display_name']}: {inst['instance_id']}" for inst in stopped_instances]
        )
        message_body = f"The following Compute instances were soft stopped for low CPU usage:\n\n{instances_details}\n"
        publish_msg_details = oci.ons.models.PublishMessageDetails(
            body=message_body,
            title=subject
        )
        ons_client.publish_message(
            topic_id=NOTIFICATION_TOPIC_OCID,
            publish_message_details=publish_msg_details
        )
        print("Notification sent.")
    else:
        print("No instances were soft stopped. No notification sent.")

    return f"Processed {len(instances)} instances. Stopped {len(stopped_instances)}."

