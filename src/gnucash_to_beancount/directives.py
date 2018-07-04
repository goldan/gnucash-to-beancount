"""Factories to transform Gnucash entities into Beancount directives.
"""
import decimal
import re

from beancount.core import data
from beancount.core.account_types import DEFAULT_ACCOUNT_TYPES as ACCOUNT_TYPES

__author__ = "Henrique Bastos <henrique@bastos.net>"
__license__ = "GNU GPLv2"


def meta_from(obj, fields):
    """Build a meta dict from fields that have values."""
    return {k: v
            for k in fields.split(' ')
            for v in (getattr(obj, k),)
            if v}


# Accounts & Open


def _get_account_types_map(acc_types):
    """Helper that maps account types from Gnucash to Beancount.

    Gnucash have 1 root account and 13 account types allowing very
    permissive account trees.

    However, Beancount restrict us to 5 root account types.

    So we need to build a map that will help us fix the account tree.
    """
    pairs = (
        ('ROOT', None),
        ('ASSET BANK CASH MUTUAL RECEIVABLE STOCK TRADING', acc_types.assets),
        ('EQUITY', acc_types.equity),
        ('EXPENSE', acc_types.expenses),
        ('INCOME', acc_types.income),
        ('LIABILITY CREDIT PAYABLE', acc_types.liabilities),
    )

    return {gnc: bc for seq, bc in pairs for gnc in seq.split(' ')}


ACCOUNT_TYPES_MAP = _get_account_types_map(ACCOUNT_TYPES)
ACCOUNT_SEP = ':'
# only alphanumeric (including non-ascii), underscores and ACCOUNT_SEP are allowed in account names
INVALID_ACCOUNT_CHARS = re.compile(r'[^\w_%s]' % ACCOUNT_SEP)


def account_name(account):
    """Returns a valid Beancount account name for a Gnucash account."""

    name = re.sub(INVALID_ACCOUNT_CHARS, '-', account.fullname)

    # If the Gnucash account is not under a valid Beancount account root
    # we must append it to the proper branch using the built account map.
    acc_type = ACCOUNT_TYPES_MAP[account.type]
    parts = name.split(ACCOUNT_SEP)
    if parts[0] != acc_type:
        parts.insert(0, acc_type)
    # Filter empty parts and uppercase first character, as beancount requires
    parts = (p[0].upper() + p[1:] for p in parts if p)

    name = ACCOUNT_SEP.join(parts)

    return name


def Open(account, date):
    meta = meta_from(account, 'code description')
    name = account_name(account)
    commodity = [account.commodity.mnemonic] if account.commodity else None

    return data.Open(meta, date, name, commodity, None)


def Commodity(commodity, date):
    meta = meta_from(commodity, 'fullname')

    return data.Commodity(meta, date, commodity.mnemonic)


def Price(price):
    meta = {}
    date = price.date
    currency = price.commodity.mnemonic
    amount = data.Amount(price.value, price.currency.mnemonic)

    return data.Price(meta, date, currency, amount)


# Postings


def units_for(split):
    # I was having balance precision problems due to how beancount deal
    # with integer precision. So multiply quantity by 1.0 to force at
    # least 1 decimal place.

    number = split.quantity * data.Decimal('1.0')
    currency = split.account.commodity.mnemonic

    return data.Amount(number, currency)


def price_for(split):
    acc_comm = split.account.commodity
    txn_comm = split.transaction.currency

    if acc_comm == txn_comm:
        return None

    try:
        number = abs(split.value / split.quantity)
    except (decimal.DivisionByZero, decimal.InvalidOperation):  # invalid operation occurs when 0/0
        if split.quantity.is_zero():
            number = decimal.Decimal('0')
    currency = txn_comm.mnemonic

    return data.Amount(number, currency)


def Posting(split):
    meta = meta_from(split, 'memo')
    account = account_name(split.account)
    cost = None
    flag = None
    units = units_for(split)
    price = price_for(split)

    return data.Posting(account, units, cost, price, flag, meta)


def Transaction(txn, postings=None):
    meta = meta_from(txn, 'num notes')
    date = txn.post_date
    flag = '*'
    payee = ''
    narration = txn.description

    postings = postings or []

    return data.Transaction(meta, date, flag, payee, narration, None, None, postings)


def TransactionWithPostings(txn):
    return Transaction(txn, [Posting(split) for split in txn.splits])
