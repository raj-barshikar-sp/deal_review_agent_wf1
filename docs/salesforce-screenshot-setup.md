# Salesforce access for the Deal Review Agent

The Deal Review Agent server reads Salesforce as **one integration user**. Every Salesforce call goes through this user: the quote and agreement documents for `/purchase-acknowledge`, and the quote lines plus the report screenshot for `/quote-lines-drs`. It only reads. It never creates, edits, or deletes Salesforce data.

Please set this up in the **full sandbox** (`https://sailpoint--full.sandbox.my.salesforce.com`). Do not use a person's login.

Engineering will send one certificate file, `sf-jwt.crt`. Upload that file. Do not create a new certificate.

## What the server reads

Everything below was checked against the full sandbox.

| Endpoint | What it does in Salesforce | Objects, fields, and report |
|---|---|---|
| `/purchase-acknowledge` | Finds the quote by its number | Quote (`SBQQ__Quote__c`): Quote Number (`Name`), Account (`SBQQ__Account__c`) |
| | Downloads the PDFs under the quote's Notes & Attachments (PO, TAF, Field Entry, signed quote) | Salesforce Files linked to the Quote (`ContentDocumentLink`, `ContentVersion`) |
| | Finds the account's Agreement SailPoint records and downloads their files (EULA, SLA, SaaS Agreement) | Agreement SailPoint (`SP_Agreement_Sailpoint__c`): `Name`, Account (`SP_Account__c`), plus Files linked to each agreement |
| | Reads the account name | Account: `Name` |
| `/quote-lines-drs` | Reads the quote lines for the DRS workbook | Quote Line (`SBQQ__QuoteLine__c`): the 13 fields in section 2 |
| | Opens the report in a browser and saves a picture | Report **NDT - Quote Lines** in the **Financial Reports** folder |

All the quote and agreement documents in the sandbox are Salesforce Files. None are classic Attachments, so no extra access is needed for Attachments.

## 1. User

Create a new user.

| Setting | Value |
|---|---|
| User License | **Salesforce** |
| Profile | **Minimum Access - Salesforce** |
| Role | None |
| Active | Yes |
| Currency | **USD** |
| Locale | English (United States) |
| Language | English |

- The license must be **Salesforce**. A Salesforce Integration license cannot open the report page, so the screenshot fails.
- Do not give this user **API Only User**, either on the profile or in any permission set. It blocks the report page.
- Currency must be **USD**. The report's "(converted)" columns and the converted prices in the workbook use the user's own currency.
- Use an email the team can read. The username must be unique across Salesforce. Send it back exactly as Salesforce shows it.
- This user never types a password. You can skip the welcome email.

## 2. Permission set

Create a permission set named **Deal Review Agent Access** and assign it to the user.

**System permissions**

- API Enabled
- Lightning Experience User
- Run Reports

**Object permissions**

Give **Read** and **View All Records** on each object below. Grant nothing else: no Create, Edit, Delete, or Modify All.

View All is needed because the user has no role and does not own any of these records.

| Object | API name | Read | View All |
|---|---|---|---|
| Account | `Account` | Yes | Yes |
| Quote | `SBQQ__Quote__c` | Yes | Yes |
| Quote Line | `SBQQ__QuoteLine__c` | Yes | Yes (if the box is greyed out, access comes through the Quote) |
| Agreement SailPoint | `SP_Agreement_Sailpoint__c` | Yes | Yes |

**Field permissions (Read)**

| Object | Fields |
|---|---|
| Quote | Account (`SBQQ__Account__c`) |
| Quote Line | Product Code (`SBQQ__ProductCode__c`), Product Name (`SBQQ__ProductName__c`), Product Family (`SBQQ__ProductFamily__c`), Quantity (`SBQQ__Quantity__c`), Effective Start Date (`SBQQ__EffectiveStartDate__c`), Effective End Date (`SBQQ__EffectiveEndDate__c`), Prorated List Price (`SBQQ__ProratedListPrice__c`), Net Unit Price (`SBQQ__NetPrice__c`), Total Discount (%) (`SBQQ__TotalDiscountRate__c`), Net Total (`SBQQ__NetTotal__c`) |
| Agreement SailPoint | Account (`SP_Account__c`) |

These fields are always readable and do not need a setting: Quote Number, Line Name, Quote (on Quote Line), Currency, Account Name, and Agreement Name.

**Files**

No extra setting is needed. A user who can read a Quote or Agreement record can open the files linked to it. Do not grant "Query All Files."

**Salesforce CPQ license**

The CPQ packages (`SBQQ`, `sbaa`) are licensed for every user in the sandbox, so nothing needs assigning. If **Setup → Installed Packages → Salesforce CPQ → Manage Licenses** asks for a seat, assign one to this user.

## 3. Report

The server uses the existing report **NDT - Quote Lines**:

- Folder: **Financial Reports**
- Developer Name: `NDT_Quote_Lines_Bgf`
- Report type: **Quote Lines**
- Format: Tabular

Do this:

1. Share the **Financial Reports** folder with this user, with at least **View** access. Folder sharing is set on the folder, not in the permission set.
2. Leave the report as it is. The server relies on the following:
   - The **first filter** is **Quote: Quote Number equals**. The server puts the quote number into the first filter. If another filter comes first, the picture shows the wrong data.
   - Show Me is **All quote lines** and Created Date is **All Time**.
   - The report name stays **NDT - Quote Lines**. The server looks the report up by this name. If it is renamed, send us the new name or the report ID.

## 4. External Client App

This one app handles both logins. **JWT Bearer** is used for the report screenshot. **Client Credentials** is used for the data and file downloads. Both log in as the integration user.

Go to **Setup → External Client App Manager → New External Client App**.

**Settings → OAuth Settings**

| Setting | Value |
|---|---|
| Enable OAuth | On |
| Callback URL | `https://localhost/callback` |
| OAuth scopes | Manage user data via APIs (`api`), Manage user data via Web browsers (`web`), Perform requests at any time (`refresh_token, offline_access`) |
| Enable JWT Bearer Flow | On. Upload `sf-jwt.crt` |
| Enable Client Credentials Flow | On |
| Issue JSON Web Token (JWT)-based access tokens | **Off** |

The callback URL is required by the form but never used. Nothing logs in through a browser, so `https://localhost/callback` is fine, now and on Cloud Run.

**Policies → Edit**

| Setting | Value |
|---|---|
| Permitted Users | **Admin approved users are pre-authorized** |
| Select Permission Sets | Add **Deal Review Agent Access** |
| Enable Client Credentials Flow | On |
| Run As (Username) | The integration user |
| IP Relaxation | Relax IP restrictions |

Two points:

- Assigning the permission set to the user is not enough. The app must list it too. Otherwise Salesforce returns "user is not admin approved to access this app."
- **Run As** must be the integration user. Otherwise the data and file calls run as someone else.

## 5. Send these back

Send the first two items in a normal message:

- The username, copied exactly
- The Consumer Key (Settings → OAuth Settings → Consumer Key and Secret)

Send the Consumer Secret through a secure channel (password manager or Secret Manager), never in chat or email.

Do not send the certificate or any private key.

## 6. Cloud Run

Nothing in Salesforce changes when the server runs on Cloud Run. Use the same user, permission set, and app. Do not create a second app.

**Network**

- Do not put Login IP Ranges on this user or its profile. Do not restrict the app to an office network. Cloud Run calls Salesforce from Google addresses that change.
- If the org has **Session Settings → Lock sessions to the IP address from which they originated** turned on, tell engineering. The server would then need a fixed outbound IP (Cloud NAT).

**Environment variables**

Store the secrets in Secret Manager. Never put them in the container image.

| Name | Value |
|---|---|
| `SALESFORCE_INSTANCE_URL` | `https://sailpoint--full.sandbox.my.salesforce.com` |
| `SALESFORCE_USERNAME` | The integration user |
| `SALESFORCE_CLIENT_ID` | Consumer Key of the app |
| `SALESFORCE_CLIENT_SECRET` | Consumer Secret of the app (Secret Manager) |
| `SALESFORCE_JWT_PRIVATE_KEY` | The private key that matches `sf-jwt.crt` (Secret Manager) |
| `SALESFORCE_QUOTE_LINES_REPORT_NAME` | `NDT - Quote Lines` |

- `SALESFORCE_QUOTE_LINES_REPORT_NAME` is required. Without it the server looks for a report with Developer Name `Quote_Lines`. The sandbox has a different report with that name, so the screenshot would show the wrong report.
- `SALESFORCE_MY_DOMAIN_URL` and `SALESFORCE_JWT_CLIENT_ID` are not needed. They default to the instance URL and client ID above.
- Do not copy a laptop `SALESFORCE_ACCESS_TOKEN` into Cloud Run. The server gets its own token.

**Service size**

At least 2 GB memory, 2 CPUs, a 300-second request timeout, and concurrency 1. One screenshot takes about a minute and runs one browser at a time.

## 7. Quick check after setup

1. Log in as an admin and open **NDT - Quote Lines**. Set the Quote Number filter to a real quote, such as `Q-127182`. Rows should appear.
2. Engineering runs `test_salesforce_ss_test.py` with `SCREENSHOT_TEST_QUOTE=Q-127182`. A PNG of that quote's lines should be saved.
3. Engineering calls `/purchase-acknowledge` with the same quote. The quote PDFs and the agreement files should download.
