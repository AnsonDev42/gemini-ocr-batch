import os
import time
from google.genai import types

from google import genai
import json

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", None))
image_files = []
for path in ["1.jpg", "2.jpg"]:
    uploaded = client.files.upload(file=path)
    image_files.append(uploaded)
    print(f"Uploaded {path} as {uploaded.name} (URI: {uploaded.uri})")

requests_data = []

# Build a request for each image.  Each request has a unique key.
for idx, file_obj in enumerate(image_files, start=1):
    requests_data.append(
        {
            "key": f"ocr_request_{idx}",
            "request": {
                "contents": [
                    {
                        "parts": [
                            {"text": "Please extract every character from this image."},
                            {
                                "file_data": {
                                    "file_uri": file_obj.uri,
                                    "mime_type": file_obj.mime_type,
                                }
                            },
                        ]
                    }
                ]
            },
        }
    )

# Save to a JSONL file (one JSON object per line)
batch_jsonl = "ocr_batch_requests.jsonl"
with open(batch_jsonl, "w") as f:
    for req in requests_data:
        f.write(json.dumps(req) + "\n")


# Upload the JSONL file
uploaded_batch_requests = client.files.upload(
    file=batch_jsonl,
    config=types.UploadFileConfig(display_name="my-ocr-batch", mime_type="jsonl"),
)
print(f"Uploaded batch request file: {uploaded_batch_requests.name}")

# Create the batch job
batch_job = client.batches.create(
    model="gemini-2.5-flash",
    src=uploaded_batch_requests.name,
    config={"display_name": "ocr-batch-job"},
)
print(f"Created batch job: {batch_job.name}")


# Poll the batch job until it finishes
completed_states = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}

while True:
    job_info = client.batches.get(name=batch_job.name)
    if job_info.state.name in completed_states:
        break
    print("Waiting for job to finish…")
    time.sleep(10)

if job_info.state.name != "JOB_STATE_SUCCEEDED":
    raise RuntimeError(f"Batch job failed with state: {job_info.state.name}")

# Download the result file (also a JSONL)
result_file_name = job_info.dest.file_name
file_bytes = client.files.download(file=result_file_name)
for line in file_bytes.decode("utf-8").splitlines():
    if not line:
        continue
    response_obj = json.loads(line)
    if "response" in response_obj:
        # Extract the text output from the first candidate
        parts = response_obj["response"]["candidates"][0]["content"]["parts"]
        for part in parts:
            if "text" in part:
                print(part["text"])
