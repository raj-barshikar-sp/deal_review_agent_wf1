# Salesforce access for the deal-review screenshot

The deal-review server signs in as one Salesforce user and saves a picture of the **Quote Lines** report. Please create that user and the app below in the enterprise sandbox. Do not use a person's login.

Engineering will send a certificate file, `sf-jwt.crt`. Upload that file. Do not create a new certificate.

## 1. User

Create a new user.

| Setting | Value |
|---|---|
| User License | Salesforce |
| Profile | Minimum Access - Salesforce |
| Active | Yes |
| Role | None |

The license must be **Salesforce**. A Salesforce Integration license or an API Only profile cannot open the report page, so the screenshot fails.

Use an email the team can read. The username must be unique in Salesforce. Send us the username exactly as Salesforce shows it.

This user never types a password. You can leave the welcome email off.

## 2. Permission set

Create a permission set named **Screenshot Bot Access** and assign it to this user.

System permissions:

- API Enabled
- Lightning Experience User
- Run Reports

Object and field access:

- Open the existing **Quote Lines** report.
- Grant **Read** on every object that report uses.
- Turn on **View All Records** for those objects, so the user can see quotes it does not own.
- Grant **Read** on every field that appears as a column.

The report folder must be shared with this user, at least **View**. Folder access is not part of the permission set. Set it on the folder.

Quote Number must be the **first filter** on that report. The server puts the quote number into that filter. If it is not first, the picture is the whole report instead of one quote. Leave the filter value blank.

## 3. External Client App

Setup → External Client App Manager → New.

| Setting | Value |
|---|---|
| Callback URL | `https://localhost/callback` |
| OAuth scopes | `api`, `web`, `refresh_token, offline_access` |
| JWT Bearer Flow | On |
| Certificate | Upload `sf-jwt.crt` |
| Issue JWT-based access tokens | Off |

Then open **Policies → Edit**:

- Permitted Users: **Admin approved users are pre-authorized**
- Under **Select Permission Sets**, add **Screenshot Bot Access**
- Save

Assigning the permission set to the user is not enough. The app must list that same permission set. If it does not, Salesforce rejects the login with "user is not admin approved to access this app."

## 4. Send these back

- Username, copied exactly
- My Domain URL, including `https://`
- Consumer Key of this app (Settings → OAuth Settings → Consumer Key and Secret). Send the key only, not the secret.
- Report name, and the report's Developer Name if it is not `Quote_Lines`

Do not send the certificate or any private key.

## 5. Cloud Run

The Salesforce user, permission set, and External Client App stay the same when the server moves to Cloud Run. Do not create a second app. The callback stays `https://localhost/callback`.

One Salesforce change matters. Do not put Login IP Ranges on this user, and do not restrict the app to an office network. Cloud Run calls Salesforce from Google addresses that change. An IP allow-list blocks the screenshot.

The private key does not go in the container image. Store it in Secret Manager and pass it as an environment variable. The image already includes Chrome.

Set these on the Cloud Run service:

| Name | Where it comes from |
|---|---|
| `SALESFORCE_MY_DOMAIN_URL` | Sandbox My Domain, including `https://`. A sandbox host contains `.sandbox.` |
| `SALESFORCE_USERNAME` | The integration user, copied exactly |
| `SALESFORCE_JWT_CLIENT_ID` | Consumer Key of this External Client App |
| `SALESFORCE_JWT_PRIVATE_KEY` | Secret Manager. The private key that matches `sf-jwt.crt` |
| `SALESFORCE_QUOTE_LINES_REPORT_NAME` | The report name, if its Developer Name is not `Quote_Lines` |

The file-download login is separate. Keep `SALESFORCE_INSTANCE_URL`, `SALESFORCE_CLIENT_ID`, and `SALESFORCE_CLIENT_SECRET` for that, also from Secret Manager. Do not copy a laptop access token into Cloud Run.

Use at least 2 GB memory, 2 CPUs, a request timeout of 300 seconds, and concurrency of 1. One screenshot takes about a minute and runs one browser at a time.
