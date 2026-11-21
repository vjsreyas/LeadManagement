from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value):
    try:
        number = Decimal(value or 0)
        return f"{number:,.0f}" if number == number.to_integral() else f"{number:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "0"


@register.filter
def display_name(user):
    return (user.get_full_name() or user.username) if user else "Unassigned"


@register.filter
def initials(user):
    return "".join(w[0] for w in display_name(user).split()[:2]).upper()
