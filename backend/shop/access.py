"""Fixed system groups and their existing capabilities. Stored role values are stable."""
from __future__ import annotations
from shop.entities import OperatorRole

# Existing business modules; enabling one never grants access to its secrets or restore actions.
MODULE_FIELDS = frozenset({
    'auto_replies_enabled', 'faq_private_enabled', 'faq_support_enabled',
    'faq_public_enabled', 'faq_admin_chat_enabled',
    'bonus_enabled', 'referral_enabled', 'volume_discount_enabled',
    'delivery_courier_enabled', 'salesdrive_enabled', 'backup_enabled',
})
INFRA_FIELDS = frozenset({
    'admin_chat_id', 'admin_ids', 'admin_topic_id', 'chat_topic_id', 'error_topic_id',
    'bot_username', 'miniapp_short_name', 'public_url',
    'timezone', 'broadcast_rate_per_second', 'broadcast_chunk',
    'quiet_hours_enabled', 'quiet_hours_start', 'quiet_hours_end',
    'backup_hour', 'backup_retention_days', 'jwt_ttl_hours',
    'salesdrive_domain', 'salesdrive_form_key', 'salesdrive_telegram_form_id',
    'salesdrive_api_key', 'salesdrive_webhook_token',
    # Site sign-in, SMS and Mini App link: keys and identities of the shop
    # itself, so only the system administrator changes them.
    'google_client_id', 'google_site_verification', 'twilio_account_sid',
    'twilio_auth_token', 'twilio_verify_service_sid', 'miniapp_url',
    'dashboard_idle_minutes',
})
# Explicit allowlist: future settings default to system-administrator access.
ADMIN_FIELDS = frozenset({
    'auto_replies_enabled',
    'backup_enabled',
    'bonus_enabled',
    'bonus_max_percent',
    'card_holder',
    'card_number',
    'cod_commission_fixed',
    'cod_commission_percent',
    'currency',
    'delivery_cost_from',
    'delivery_courier_enabled',
    'delivery_days',
    'delivery_weight_per_item',
    'faq_admin_chat_enabled',
    'faq_private_enabled',
    'faq_public_enabled',
    'faq_support_enabled',
    'instagram_url',
    'min_age',
    'novaposhta_api_key',
    'novaposhta_cargo_description',
    'novaposhta_sender_city',
    'novaposhta_sender_phone',
    'novaposhta_sender_warehouse',
    'novaposhta_sender_warehouse_ref',
    'privacy_url',
    'referral_enabled',
    'referral_percent',
    'salesdrive_enabled',
    'salesdrive_payment_map',
    'salesdrive_shipping_map',
    'salesdrive_site',
    'salesdrive_status_map',
    'seller_address',
    'seller_code',
    'seller_email',
    'seller_name',
    'seller_phone',
    'shop_name',
    'terms_url',
    'tiktok_url',
    'volume_discount_enabled',
    'volume_discount_min',
    'volume_discount_percent',
})

# A10: менеджер — продажі, клієнти, підтримка й читання каталогу. Зміни
# каталогу (ціни, публікація, залишки, імпорт, видалення) та весь маркетинг
# (промокоди, розсилки) — лише адміністратор. API перевіряє це
# через require_admin; ця таблиця — та сама матриця для UI й тестів.
_MANAGER = frozenset({'sales.manage', 'customers.manage', 'support.manage', 'catalog.read'})
_ADMIN = _MANAGER | {'catalog.manage', 'marketing.manage', 'blog.manage', 'settings.manage',
                     'modules.manage', 'operators.manage'}
ROLE_PERMISSIONS = {
    OperatorRole.MANAGER: _MANAGER,
    OperatorRole.ADMIN: frozenset(_ADMIN),
    OperatorRole.SYSADMIN: frozenset(_ADMIN | {'system.manage'}),
}


def permissions_for(role: OperatorRole) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, ()))


def editable_settings(role: OperatorRole, fields) -> frozenset[str]:
    if role == OperatorRole.SYSADMIN:
        return frozenset(fields)
    if role == OperatorRole.ADMIN:
        return frozenset(fields) & ADMIN_FIELDS
    return frozenset()


def assignable_roles(role: OperatorRole) -> tuple[OperatorRole, ...]:
    if role == OperatorRole.SYSADMIN:
        return (OperatorRole.MANAGER, OperatorRole.ADMIN)
    if role == OperatorRole.ADMIN:
        return (OperatorRole.MANAGER,)
    return ()


def can_manage_operator(actor_role: OperatorRole, target_role: OperatorRole) -> bool:
    return actor_role == OperatorRole.SYSADMIN or (
        actor_role == OperatorRole.ADMIN and target_role == OperatorRole.MANAGER
    )
