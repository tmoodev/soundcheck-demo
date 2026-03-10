"""
Dashboard queries using tenant-scoped plaid_ingest models.
All queries are automatically scoped to the current tenant via django-tenants.
"""
from decimal import Decimal

from django.db.models import Q, Sum, F, Value, Case, When, DecimalField, BooleanField
from django.db.models.functions import Abs, Coalesce

from clients.models import ClientAccount
from plaid_ingest.models import PlaidAccount, PlaidAccountBalance, PlaidTransaction


def _get_account_ids_for_client(client_id):
    """Return list of account_ids mapped to a client, or None if no filter."""
    if not client_id:
        return None
    return list(
        ClientAccount.objects.filter(client_id=client_id).values_list("account_id", flat=True)
    )


def _account_filter(queryset, account_ids, account_id_field="account_id"):
    """Apply account_id filtering to a queryset."""
    if account_ids is None:
        return queryset
    return queryset.filter(**{f"{account_id_field}__in": account_ids})


# ---------------------------------------------------------------------------
# Summary KPIs
# ---------------------------------------------------------------------------
def get_summary_kpis(client_id=None):
    """Return dict with total_balance, total_available, total_pending."""
    account_ids = _get_account_ids_for_client(client_id)

    # Balance KPIs
    bal_qs = PlaidAccountBalance.objects.all()
    if account_ids is not None:
        bal_qs = bal_qs.filter(account__account_id__in=account_ids)

    agg = bal_qs.aggregate(
        total_balance=Coalesce(Sum("current_balance"), Decimal("0")),
        total_available=Coalesce(Sum("available_balance"), Decimal("0")),
    )

    # Pending transactions (no date filter)
    txn_qs = PlaidTransaction.objects.filter(pending=True)
    if account_ids is not None:
        txn_qs = txn_qs.filter(account__account_id__in=account_ids)

    pending_agg = txn_qs.aggregate(
        total_pending=Coalesce(Sum(Abs("amount")), Decimal("0")),
    )

    return {
        "total_balance": agg["total_balance"],
        "total_available": agg["total_available"],
        "total_pending": pending_agg["total_pending"],
    }


# ---------------------------------------------------------------------------
# Accounts Table
# ---------------------------------------------------------------------------
ACCOUNTS_COLUMNS = [
    "account_name", "institution_name", "type", "subtype", "mask",
    "current_balance", "available_balance", "credit_limit",
    "utilization_pct", "is_overdrawn", "balance_as_of",
]

ACCOUNTS_SORTABLE = {
    "account_name", "institution_name", "type", "subtype", "mask",
    "current_balance", "available_balance", "credit_limit",
    "utilization_pct", "balance_as_of",
}

ACCOUNTS_SEARCH_FIELDS = ["account_name", "institution_name", "mask"]

# Map frontend sort keys to ORM field paths
_ACCOUNTS_SORT_MAP = {
    "account_name": "name",
    "institution_name": "item__institution_name",
    "type": "type",
    "subtype": "subtype",
    "mask": "mask",
    "current_balance": "balance__current_balance",
    "available_balance": "balance__available_balance",
    "credit_limit": "balance__credit_limit",
    "utilization_pct": "balance__credit_limit",  # Computed; approximate sort
    "balance_as_of": "balance__as_of",
}


def get_accounts_page(client_id=None, search="", sort="account_name", order="asc",
                      page=1, page_size=25):
    """Return paginated accounts with total count."""
    account_ids = _get_account_ids_for_client(client_id)

    qs = PlaidAccount.objects.select_related("item", "balance")
    if account_ids is not None:
        qs = qs.filter(account_id__in=account_ids)

    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(item__institution_name__icontains=search)
            | Q(mask__icontains=search)
        )

    # Sort
    if sort not in ACCOUNTS_SORTABLE:
        sort = "account_name"
    if order not in ("asc", "desc"):
        order = "asc"

    orm_sort = _ACCOUNTS_SORT_MAP.get(sort, "name")
    if order == "desc":
        orm_sort = f"-{orm_sort}"
    qs = qs.order_by(orm_sort)

    total = qs.count()
    offset = (page - 1) * page_size
    accounts = qs[offset:offset + page_size]

    rows = []
    for acct in accounts:
        bal = getattr(acct, "balance", None)
        current = bal.current_balance if bal else None
        available = bal.available_balance if bal else None
        credit_limit = bal.credit_limit if bal else None
        credit_remaining = bal.credit_remaining if bal else None

        # Compute utilization
        utilization_pct = None
        if credit_limit and credit_limit > 0 and credit_remaining is not None:
            utilization_pct = float((credit_limit - credit_remaining) / credit_limit * 100)

        rows.append({
            "account_id": acct.account_id,
            "account_name": acct.name,
            "institution_name": acct.item.institution_name if acct.item else "",
            "type": acct.type,
            "subtype": acct.subtype,
            "mask": acct.mask,
            "current_balance": current,
            "available_balance": available,
            "credit_limit": credit_limit,
            "utilization_pct": utilization_pct,
            "is_overdrawn": current < 0 if current is not None else False,
            "balance_as_of": bal.as_of if bal else None,
        })

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


# ---------------------------------------------------------------------------
# Transactions Table
# ---------------------------------------------------------------------------
TRANSACTIONS_SORTABLE = {
    "transaction_date", "transaction_name", "merchant_name", "amount",
    "account_name", "institution_name", "payment_channel", "transaction_type",
    "flow_direction", "pending",
}

_TRANSACTIONS_SORT_MAP = {
    "transaction_date": "date",
    "transaction_name": "name",
    "merchant_name": "merchant_name",
    "amount": "amount",
    "account_name": "account__name",
    "institution_name": "account__item__institution_name",
    "payment_channel": "payment_channel",
    "transaction_type": "transaction_type",
    "flow_direction": "amount",  # Approximate: inflow = negative amount
    "pending": "pending",
}


def get_transactions_page(client_id=None, account_id=None, date_from=None,
                          date_to=None, pending=None, search="",
                          sort="transaction_date", order="desc",
                          page=1, page_size=25):
    """Return paginated transactions with total count."""
    account_ids = _get_account_ids_for_client(client_id)
    if account_id:
        if account_ids is not None:
            if account_id in account_ids:
                account_ids = [account_id]
            else:
                account_ids = []
        else:
            account_ids = [account_id]

    qs = PlaidTransaction.objects.select_related("account", "account__item")
    if account_ids is not None:
        qs = qs.filter(account__account_id__in=account_ids)

    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if pending is not None:
        qs = qs.filter(pending=pending)
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(merchant_name__icontains=search)
        )

    # Sort
    if sort not in TRANSACTIONS_SORTABLE:
        sort = "transaction_date"
    if order not in ("asc", "desc"):
        order = "desc"

    orm_sort = _TRANSACTIONS_SORT_MAP.get(sort, "date")
    if order == "desc":
        orm_sort = f"-{orm_sort}"
    qs = qs.order_by(orm_sort)

    total = qs.count()
    offset = (page - 1) * page_size
    txns = qs[offset:offset + page_size]

    rows = []
    for txn in txns:
        amount = txn.amount
        amount_abs = abs(amount) if amount is not None else None
        flow_direction = "INFLOW" if amount and amount < 0 else "OUTFLOW"

        rows.append({
            "transaction_id": txn.transaction_id,
            "transaction_date": txn.date,
            "transaction_name": txn.name,
            "merchant_name": txn.merchant_name,
            "amount": amount,
            "amount_abs": amount_abs,
            "pending": txn.pending,
            "account_name": txn.account.name if txn.account else "",
            "account_id": txn.account.account_id if txn.account else "",
            "institution_name": (
                txn.account.item.institution_name
                if txn.account and txn.account.item else ""
            ),
            "payment_channel": txn.payment_channel,
            "transaction_type": txn.transaction_type,
            "category_id": txn.category_id,
            "flow_direction": flow_direction,
            "iso_currency_code": txn.iso_currency_code,
        })

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


# ---------------------------------------------------------------------------
# CSV Export (transactions)
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "transaction_date", "transaction_name", "merchant_name", "amount", "pending",
    "account_name", "institution_name", "payment_channel", "transaction_type",
    "category_id", "flow_direction",
]


def get_transactions_for_export(client_id=None, account_id=None, date_from=None,
                                date_to=None, pending=None, search="",
                                max_rows=250_000):
    """Return (rows, total_count, exceeded). If exceeded, rows is empty."""
    account_ids = _get_account_ids_for_client(client_id)
    if account_id:
        if account_ids is not None:
            if account_id in account_ids:
                account_ids = [account_id]
            else:
                account_ids = []
        else:
            account_ids = [account_id]

    qs = PlaidTransaction.objects.select_related("account", "account__item")
    if account_ids is not None:
        qs = qs.filter(account__account_id__in=account_ids)

    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if pending is not None:
        qs = qs.filter(pending=pending)
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(merchant_name__icontains=search)
        )

    qs = qs.order_by("-date")
    total = qs.count()

    if total > max_rows:
        return [], total, True

    txns = qs[:max_rows]
    rows = []
    for txn in txns:
        amount = txn.amount
        flow_direction = "INFLOW" if amount and amount < 0 else "OUTFLOW"
        rows.append((
            txn.date,
            txn.name,
            txn.merchant_name,
            amount,
            txn.pending,
            txn.account.name if txn.account else "",
            txn.account.item.institution_name if txn.account and txn.account.item else "",
            txn.payment_channel,
            txn.transaction_type,
            txn.category_id,
            flow_direction,
        ))

    return rows, total, False


def get_account_options(client_id=None):
    """Return list of (account_id, label) for filter dropdowns."""
    account_ids = _get_account_ids_for_client(client_id)

    qs = PlaidAccount.objects.all().order_by("name")
    if account_ids is not None:
        qs = qs.filter(account_id__in=account_ids)

    return [(acct.account_id, f"{acct.name} ({acct.mask})") for acct in qs]
