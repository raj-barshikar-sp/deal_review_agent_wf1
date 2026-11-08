# Access the deal review server

Open [https://deal-review-agent-236208394643.asia-south1.run.app](https://deal-review-agent-236208394643.asia-south1.run.app).

The page has two sides:

- **Purchase acknowledgement.** Enter the email subject and body, then click **Send purchase acknowledgement**. The subject must end with ` - Purchase Acknowledgement for SailPoint Offerings`. The body must contain one quote number like `Q-127182`.
- **Quote lines.** Enter a quote number `Q-XXXXXX`, then click **Fetch quote lines**.

A browser request with no Google login gets **403**. Sign in as a user who can invoke the service, or proxy it locally:

```bash
gcloud run services proxy deal-review-agent --region asia-south1 --port 8080
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080).

The same calls from a terminal:

```bash
TOKEN=$(gcloud auth print-identity-token)
URL=https://deal-review-agent-236208394643.asia-south1.run.app

curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"subject":"Fidelity Investments - Purchase Acknowledgement for SailPoint Offerings","body":"Signed quote Q-127182."}' \
  "$URL/purchase-acknowledge"

curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"quote_number":"Q-127182"}' \
  "$URL/quote-lines-drs"
```
