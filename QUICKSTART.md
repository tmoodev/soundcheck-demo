# SoundCheck Financial — Quick Start Guide

Welcome to SoundCheck Financial. This guide walks you through getting set up from first login to a fully connected dashboard.

---

## Step 1 — Log In

Navigate to your organization's dashboard URL (provided by your administrator):

- **Example:** `https://clineco.soundcheckfinancial.com`

Enter your email and temporary password. You will be prompted to set a new password immediately.

---

## Step 2 — Set Up Two-Factor Authentication (MFA)

After setting your password, you will be asked to configure MFA. This is required and cannot be skipped.

1. Open an authenticator app on your phone (Google Authenticator, Authy, or any TOTP app)
2. Scan the QR code displayed on screen
3. Enter the 6-digit code from the app to confirm
4. **Save your recovery codes** — copy them somewhere safe. These are the only way to access your account if you lose your phone.

From this point on, every login will ask for your email, password, and a 6-digit code from your authenticator app.

---

## Step 3 — Connect a Bank Account

Go to **Manage → Bank Connections → Connect New Bank**

This opens Plaid Link, a secure bank connection flow:

1. Search for your bank or financial institution
2. Enter your online banking credentials (these are sent directly to your bank — SoundCheck never sees them)
3. Select which accounts to share
4. Click **Connect**

Supported account types: checking, savings, credit cards, loans, and investment accounts.

Once connected, your accounts and balances will appear immediately. Transactions will begin syncing in the background.

> **Note:** You can connect multiple banks. Each connection appears as a separate entry under Bank Connections.

---

## Step 4 — Add Clients

Clients are the people or entities whose accounts you are monitoring. Go to **Manage → Clients → Create Client**.

Enter the client's name and save. Repeat for each client you manage.

---

## Step 5 — Map Accounts to Clients

After adding clients, link their bank accounts to them:

1. Go to **Manage → Clients**
2. Click **Add Accounts** next to a client
3. Select the bank accounts that belong to that client
4. Save

Accounts mapped to a client will appear under that client's filter in the dashboard.

---

## Step 6 — View the Dashboard

The **Dashboard → Summary** page shows:

| Section | What it shows |
|---------|---------------|
| **Total Balance** | Combined current balance across all accounts |
| **Total Available** | Combined available funds |
| **Total Pending** | Pending transactions not yet settled |
| **Accounts table** | All accounts with balance, available, credit limit, utilization %, and overdraft status |

**Filter by client** using the dropdown at the top to focus on one client's accounts.

**Sort** any column by clicking the column header.

**Search** accounts by name, institution, or account number using the search box.

---

## Step 7 — View Transactions

Go to **Dashboard → Transactions** to see a full transaction history across all connected accounts. You can filter by client, date range, and account, and export to CSV using the export button.

---

## Managing Bank Connections

From **Manage → Bank Connections** you can:

- **Sync Transactions** — pull the latest transactions for a connection
- **Refresh Balances** — update current balance figures immediately
- View connection status (Active / Error / Revoked)

Transactions also sync automatically in response to Plaid webhooks — you typically do not need to sync manually.

---

## Managing Users

Admins can add additional users under **Manage → Users → Create User**. Each user gets their own login and must set up MFA on first sign-in.

To reset a user's MFA or password, go to **Manage → Users**, click the user, and use the available actions.

---

## Frequently Asked Questions

**Can I connect a credit card?**
Yes. Credit card accounts are fully supported. The dashboard shows your current balance, credit limit, and utilization percentage.

**What if my bank connection shows an error?**
Go to **Manage → Bank Connections** and reconnect the affected institution. Errors usually occur when your bank requires you to re-authenticate (e.g., after a password change).

**How often do transactions sync?**
Automatically via Plaid webhooks — typically within minutes of a transaction posting. You can also sync manually at any time.

**I lost my MFA device — what do I do?**
Use one of your recovery codes on the login screen. If you no longer have your recovery codes, contact your administrator to reset your MFA.

---

*For administrator or technical support, refer to `agent.md`.*
