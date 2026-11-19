from aiogram.fsm.state import State, StatesGroup


class Checkout(StatesGroup):
    name = State()
    phone = State()
    city = State()
    address = State()
    promo = State()
    bonus = State()
    payment = State()
    comment = State()
    confirm = State()
    receipt = State()


class PhoneConfirm(StatesGroup):
    """Website profile asked the bot to confirm the phone (start=vp_<token>)."""
    waiting = State()
