from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot import texts
from bot.states import PhoneConfirm
from shop.services import phone_verification
from shop.services.shop_settings import get_shop_settings
from shop.entities import User
from shop.repo.base import Repository

router = Router()


async def _offer_shop(message: Message) -> None:
    """Канонічна кнопка Named Mini App під повідомленням.

    Вона веде на ``https://t.me/elfarshop_bot/elfar``: Telegram сам створює
    WebApp-контекст і передає initData, тому кнопка не залежить від PUBLIC_URL
    та кешу старого домену.
    """
    await message.answer(texts.OPEN_SHOP_HINT, reply_markup=kb.open_shop())


@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject | None,
    repo: Repository, user: User, state: FSMContext,
) -> None:
    await state.clear()

    # Реферальне посилання: t.me/bot?start=ABCD1234
    payload = command.args if command else None
    token = phone_verification.token_from_start(payload)
    if token:
        await _start_phone_confirmation(message, state, repo, token)
        return
    # RepositoryMiddleware уже скидає позначку на будь-якому приватному
    # апдейті. Перевірка лишається як страховка для прямого виклику хендлера
    # в тесті або майбутнього режиму без цього middleware.
    if not user.bot_reachable:
        await repo.set_bot_reachable(user.tg_id, True)
        user.bot_reachable = True

    if payload and not user.referrer_id:
        referrer = await repo.get_user_by_referral_code(payload.strip())
        if referrer and referrer.id != user.id:
            await repo.set_user_referrer(user, referrer.id)

    shop = await get_shop_settings(repo)
    await message.answer(
        texts.WELCOME.format(shop=escape(shop.shop_name)), reply_markup=kb.main_menu()
    )
    await _offer_shop(message)


@router.callback_query(F.data.in_({"age:yes", "age:no"}))
async def legacy_age_button(callback: CallbackQuery, repo: Repository) -> None:
    """Кнопки підтвердження віку зі старих повідомлень. Віку більше не
    перевіряємо (парфумерія), тож просто відкриваємо меню."""
    shop = await get_shop_settings(repo)
    await callback.message.answer(
        texts.WELCOME.format(shop=escape(shop.shop_name)), reply_markup=kb.main_menu()
    )
    await _offer_shop(callback.message)
    await callback.answer()


@router.message(F.text == "🛍 Відкрити магазин")
@router.message(Command("shop", "magazin", "katalog"))
async def cmd_shop(message: Message, repo: Repository, user: User) -> None:
    """Головна команда магазину.

    Окремо від /start: /start у Telegram — це «почати спочатку», його
    натискають раз. Для повернення в магазин потрібна своя команда, яка
    видно в меню поруч із полем вводу.
    """
    shop = await get_shop_settings(repo)
    await message.answer(
        texts.WELCOME.format(shop=escape(shop.shop_name)), reply_markup=kb.main_menu()
    )
    await _offer_shop(message)


@router.message(F.text == "ℹ️ Довідка")
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP, reply_markup=kb.main_menu())


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ------------------------------------------------ website phone confirmation

PHONE_ASK = ("Підтвердження номера для сайту {shop}.\n\n"
             "Натисніть кнопку «📱 Надіслати номер» нижче: Telegram передасть номер, "
             "прив’язаний до вашого акаунта. Вводити його вручну не потрібно.")
PHONE_DONE = ("✅ Номер {phone} підтверджено. Поверніться на сайт — профіль оновиться сам.")
PHONE_DONE_LINKED = PHONE_DONE + "\nІсторію покупок із Telegram теж підключено до профілю сайту."
PHONE_EXPIRED = ("Посилання для підтвердження застаріло або вже використане. "
                 "Відкрийте профіль на сайті й натисніть «Підтвердити через Telegram» ще раз.")
PHONE_OTHER = ("Цей профіль сайту вже пов’язаний з іншим Telegram-акаунтом. "
               "Підтвердіть номер з того акаунта.")
PHONE_FOREIGN = "Надішліть саме свій номер кнопкою «📱 Надіслати номер», а не чужий контакт."
PHONE_NOT_UA = "Сайт приймає лише українські номери (+380). Цей номер підтвердити не вийде."


async def _start_phone_confirmation(message: Message, state: FSMContext, repo: Repository, token: str) -> None:
    if await phone_verification.pending_request(repo.s, token) is None:
        await message.answer(PHONE_EXPIRED, reply_markup=kb.main_menu())
        return
    shop = await get_shop_settings(repo)
    await state.set_state(PhoneConfirm.waiting)
    await state.update_data(phone_token=token)
    await message.answer(PHONE_ASK.format(shop=escape(shop.shop_name)), reply_markup=kb.PHONE_REQUEST)


@router.message(PhoneConfirm.waiting, F.contact)
async def phone_confirmation_contact(message: Message, state: FSMContext, repo: Repository, user: User) -> None:
    # Telegram sets contact.user_id to the sender only for their own number.
    if message.contact.user_id != message.from_user.id:
        await message.answer(PHONE_FOREIGN, reply_markup=kb.PHONE_REQUEST)
        return
    phone = phone_verification.normalize_ua_phone(message.contact.phone_number)
    if not phone:
        await state.clear()
        await message.answer(PHONE_NOT_UA, reply_markup=kb.main_menu())
        return
    token = (await state.get_data()).get("phone_token") or ""
    result = await phone_verification.confirm_with_telegram(repo.s, token, user.id, phone)
    await state.clear()
    text = {"ok": PHONE_DONE, "ok_linked": PHONE_DONE_LINKED,
            "other_telegram": PHONE_OTHER}.get(result, PHONE_EXPIRED)
    await message.answer(text.format(phone=phone), reply_markup=kb.main_menu())

