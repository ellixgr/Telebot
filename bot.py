import os
import uuid
import time
import asyncio
import requests
import threading
import random
import re
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    TypeHandler,
    ContextTypes,
    ApplicationHandlerStop,
    ChatMemberHandler
)

# ==============================================
# ✅ CONFIGURAÇÕES
# ==============================================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", -1004399892914))
MONGO_URI = os.environ.get("MONGO_URI")

# ==============================================
# ✅ CONEXÃO BANCO DE DADOS
# ==============================================
try:
    mongo_client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        tlsAllowInvalidCertificates=True
    )
    db = mongo_client["sanizinhabot_db"]
    collection_clientes = db["clientes"]
    collection_chats = db["chats_autorizados"]
    print("✅ Conectado ao MongoDB com sucesso!")
except Exception as e:
    print(f"❌ ERRO NO BANCO: {e}")
    exit(1)

# ==============================================
# ✅ VARIÁVEIS GLOBAIS
# ==============================================
TEMPO_INICIAL = time.time()
ultimo_envio = {}
contador_spam = {}
usuarios_bloqueados = {}
bloqueio_temporario = {}
pagamentos_notificados = set()

# ==============================================
# ✅ INTERCEPTADOR CORRIGIDO
# ==============================================
async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.new_chat_members:
        return

    user = update.effective_user
    if not user:
        return
    user_id = user.id
    agora = time.time()

    if user_id == DONO_ID:
        return

    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        if cmd not in ['/start', '/suporte', '/suport', '/id', '/ping']:
            raise ApplicationHandlerStop

    if user_id in bloqueio_temporario:
        if bloqueio_temporario[user_id] - agora > 0:
            raise ApplicationHandlerStop
        else:
            del bloqueio_temporario[user_id]
            contador_spam.pop(user_id, None)

    if user_id in usuarios_bloqueados:
        raise ApplicationHandlerStop

    if user_id in ultimo_envio:
        if agora - ultimo_envio[user_id] < 1.2:
            contador_spam[user_id] = contador_spam.get(user_id, 0) + 1
            ultimo_envio[user_id] = agora
            if contador_spam[user_id] >= 8:
                bloqueio_temporario[user_id] = agora + 300
                contador_spam[user_id] = 0
                if update.effective_chat.type == "private":
                    try:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text="⚠️ **Muitas mensagens rápidas! Aguarde alguns instantes.**",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                raise ApplicationHandlerStop
            raise ApplicationHandlerStop

    ultimo_envio[user_id] = agora

# ==============================================
# ✅ SALVA GRUPOS/CANAIS AUTOMATICAMENTE
# ==============================================
async def verificar_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    new_status = result.new_chat_member.status

    if chat.type in ["group", "supergroup", "channel"]:
        try:
            if new_status in ["member", "administrator"]:
                collection_chats.update_one(
                    {"chat_id": chat.id},
                    {"$set": {"chat_id": chat.id, "title": chat.title, "type": chat.type}},
                    upsert=True
                )
                print(f"✅ Salvo: {chat.title} | ID: {chat.id}")
            elif new_status in ["left", "kicked"]:
                collection_chats.delete_one({"chat_id": chat.id})
                print(f"❌ Removido: {chat.title}")
        except Exception as e:
            print(f"⚠️ Erro ao salvar chat: {e}")

# ==============================================
# ✅ COMANDO /START
# ==============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    usuario_mencao = f"@{user.username}" if user.username else user.first_name or "Usuário"

    texto_boas_vindas = (
        f"Olá {usuario_mencao}! 🥳\n\n"
        "Acesse MILHARES de mídias exclusivas por preços baixos!\n"
        "Escolha abaixo o plano que você quer:"
    )

    keyboard = [
        [InlineKeyboardButton("⚡ 1 HORA → R$ 0,60", callback_data="comprar_0.60")],
        [InlineKeyboardButton("📅 1 DIA → R$ 2,50", callback_data="comprar_2.50")],
        [InlineKeyboardButton("🗓️ 1 SEMANA → R$ 7,00", callback_data="comprar_7.00")],
        [InlineKeyboardButton("📆 1 MÊS → R$ 20,00", callback_data="comprar_20.00")],
        [InlineKeyboardButton("♾️ PERMANENTE → R$ 60,00", callback_data="comprar_60.00")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    midia_ok = False
    try:
        async for msg in context.bot.get_chat_history(chat_id=CANAL_ALVO_ID, limit=50):
            if msg.photo:
                await update.message.reply_photo(
                    photo=msg.photo[-1].file_id,
                    caption=texto_boas_vindas,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                    protect_content=True
                )
                midia_ok = True
                break
            elif msg.video and not msg.video.is_animation:
                await update.message.reply_video(
                    video=msg.video.file_id,
                    caption=texto_boas_vindas,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                    protect_content=True
                )
                midia_ok = True
                break
    except Exception as e:
        print(f"⚠️ Erro ao pegar mídia: {e}")

    if not midia_ok:
        await update.message.reply_text(texto_boas_vindas, reply_markup=reply_markup, parse_mode="Markdown")

# ==============================================
# ✅ COMANDOS DO DONO
# ==============================================
async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    chat = update.effective_chat
    user = update.effective_user
    await update.message.reply_text(
        f"📊 **INFORMAÇÕES:**\n\n"
        f"💬 Chat: {chat.title or 'Privado'}\n"
        f"🆔 ID Chat: `{chat.id}`\n"
        f"👤 Seu ID: `{user.id}`",
        parse_mode="Markdown"
    )

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    inicio = time.time()
    msg = await update.message.reply_text("🏓 PINGANDO...")
    latencia = int((time.time() - inicio) * 1000)
    uptime = int(time.time() - TEMPO_INICIAL)
    await msg.edit_text(
        f"🏓 **PONG!**\n\n"
        f"⚡ Latência: `{latencia}ms`\n"
        f"⏳ Online há: `{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s`",
        parse_mode="Markdown"
    )

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 **SUPORTE**\n\n"
        "Fale comigo: @Lyhhxv",
        parse_mode="Markdown"
    )

async def addusuario_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ Use: `/addusuario <ID> <VALOR>`\nExemplo: `/addusuario 123456 0.60`",
            parse_mode="Markdown"
        )
        return

    try:
        user_id = int(args[0])
        valor = float(re.sub(r'[^0-9.]', '', args[1]))
        if valor == 0.60:
            seg = 3600
            nome = "1 Hora"
        elif valor == 2.50:
            seg = 86400
            nome = "1 Dia"
        elif valor == 7.00:
            seg = 86400*7
            nome = "7 Dias"
        elif valor == 20.00:
            seg = 86400*30
            nome = "30 Dias"
        elif valor == 60.00:
            seg = 86400*365*10
            nome = "Permanente"
        else:
            seg = int(valor)*86400
            nome = f"{int(valor)} Dias"

        expira = time.time() + seg
        collection_clientes.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "nome": "Adicionado Manual", "expira_em": expira}},
            upsert=True
        )
        await update.message.reply_text(f"✅ Adicionado! Plano: {nome}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def delusuario_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠️ Use: `/delusuario <ID>`")
        return
    try:
        user_id = int(context.args[0])
        res = collection_clientes.delete_one({"user_id": user_id})
        if res.deleted_count:
            await update.message.reply_text(f"✅ Removido: {user_id}")
        else:
            await update.message.reply_text("❌ Não encontrado")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

# ==============================================
# ✅ PAGAMENTO MERCADO PAGO CORRIGIDO
# ==============================================
async def gerar_pagamento(valor, user, bot):
    url = "https://api.mercadopago.com/v1/payments"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4())
    }
    payload = {
        "transaction_amount": valor,
        "description": f"Acesso VIP - R$ {valor:.2f}",
        "payment_method_id": "pix",
        "payer": {
            "email": f"user_{user.id}@telegram.com",
            "first_name": user.first_name or "Cliente",
            "last_name": user.last_name or "Telegram"
        }
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 201:
            dados = resp.json()
            qr = dados.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code")
            return True, dados["id"], qr
        else:
            print(f"❌ ERRO MP: {resp.status_code} | {resp.text[:300]}")
            return False, None, f"Erro API: {resp.status_code}"
    except Exception as e:
        print(f"❌ ERRO CONEXÃO MP: {e}")
        return False, None, f"Erro de conexão: {str(e)}"

async def verificar_pagamento(pag_id):
    url = f"https://api.mercadopago.com/v1/payments/{pag_id}"
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            dados = resp.json()
            return dados.get("status") == "approved", dados.get("transaction_amount", 0)
        return False, 0
    except:
        return False, 0

# ==============================================
# ✅ BOTÕES E AÇÕES
# ==============================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dados = query.data

    if dados.startswith("comprar_"):
        valor = float(dados.split("_")[1])
        await query.edit_message_text("⏳ Gerando seu PIX, aguarde...")
        ok, pag_id, qr = await gerar_pagamento(valor, update.effective_user, context.bot)
        if ok:
            await query.message.reply_text(
                f"✅ **PIX GERADO!**\n\n💰 Valor: R$ {valor:.2f}\n\n📋 Copia e cola:\n`{qr}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Copiar PIX", copy_text=qr)],
                    [InlineKeyboardButton("🔄 Verificar Pagamento", callback_data=f"check_{pag_id}")]
                ])
            )
        else:
            await query.message.reply_text(f"❌ {qr}")

    elif dados.startswith("check_"):
        pag_id = dados.split("_")[1]
        aprovado, valor_pago = await verificar_pagamento(pag_id)
        if aprovado:
            await query.answer("🎉 PAGAMENTO APROVADO!", show_alert=True)
            if valor_pago == 0.60:
                seg = 3600
                nome = "1 Hora"
            elif valor_pago == 2.50:
                seg = 86400
                nome = "1 Dia"
            elif valor_pago == 7.00:
                seg = 86400*7
                nome = "7 Dias"
            elif valor_pago == 20.00:
                seg = 86400*30
                nome = "30 Dias"
            elif valor_pago == 60.00:
                seg = 86400*365*10
                nome = "Permanente"
            else:
                seg = int(valor_pago)*86400
                nome = f"{int(valor_pago)} Dias"

            user_id = update.effective_user.id
            collection_clientes.update_one(
                {"user_id": user_id},
                {"$set": {
                    "user_id": user_id,
                    "nome": update.effective_user.first_name or "Cliente",
                    "expira_em": time.time() + seg
                }},
                upsert=True
            )

            link = None
            try:
                convite = await context.bot.create_chat_invite_link(CANAL_ALVO_ID, member_limit=1)
                link = convite.invite_link
            except:
                pass

            msg_link = f"Aqui seu acesso: {link}" if link else "Contate @Lyhhxv para liberar."
            await query.message.reply_text(
                f"🎉 **PAGAMENTO CONFIRMADO!**\n\n✅ Plano: {nome}\n💰 Valor: R$ {valor_pago:.2f}\n\n{msg_link}",
                parse_mode="Markdown"
            )

            if pag_id not in pagamentos_notificados:
                pagamentos_notificados.add(pag_id)
                await context.bot.send_message(
                    DONO_ID,
                    f"🚨 NOVA VENDA!\n👤 {update.effective_user.first_name}\n🆔 {user_id}\n💰 R$ {valor_pago:.2f}\n📦 {nome}",
                    parse_mode="Markdown"
                )
        else:
            await query.message.reply_text("⏳ Pagamento não confirmado ainda. Pague e clique novamente.", parse_mode="Markdown")

# ==============================================
# ✅ GERENCIADOR DE ASSINATURAS
# ==============================================
async def gerenciador(app):
    await asyncio.sleep(15)
    while True:
        try:
            agora = time.time()
            for cliente in collection_clientes.find():
                user_id = cliente["user_id"]
                expira = cliente["expira_em"]
                restante = expira - agora

                if 0 < restante <= 1200 and not cliente.get("aviso"):
                    try:
                        await app.bot.send_message(
                            user_id,
                            "⚠️ SEU PLANO ACABA EM 20 MINUTOS!\nRenove para não perder acesso.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Renovar", callback_data="start")]])
                        )
                        collection_clientes.update_one({"user_id": user_id}, {"$set": {"aviso": True}})
                    except:
                        pass

                elif restante <= 0:
                    try:
                        await app.bot.ban_chat_member(CANAL_ALVO_ID, user_id)
                        await app.bot.unban_chat_member(CANAL_ALVO_ID, user_id)
                        await app.bot.send_message(user_id, "❌ SEU PLANO EXPIROU!\nCompre novamente com /start")
                    except:
                        pass
                    collection_clientes.delete_one({"user_id": user_id})
        except Exception as e:
            print(f"⚠️ Erro gerenciador: {e}")
        await asyncio.sleep(60)

def run_gerenciador(app):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(gerenciador(app))

# ==============================================
# ✅ INICIO DO BOT
# ==============================================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    try:
        from bemvindo import registrar_bemvindo
        registrar_bemvindo(app)
        print("✅ Bem-vindo carregado!")
    except:
        print("⚠️ Sem módulo bem-vindo")

    threading.Thread(target=run_gerenciador, args=(app,), daemon=True).start()

    app.add_handler(TypeHandler(Update, interceptador_universal), group=-1)
    app.add_handler(ChatMemberHandler(verificar_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler(["suporte", "suport"], suporte_cmd))
    app.add_handler(CommandHandler("addusuario", addusuario_cmd))
    app.add_handler(CommandHandler("delusuario", delusuario_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ BOT ONLINE E FUNCIONANDO!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
