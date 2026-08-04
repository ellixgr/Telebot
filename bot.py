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

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# ==============================================
# ✅ PEGA TUDO DAS VARIÁVEIS DO RENDER!
# ==============================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")

# ⚠️ Se a chave estiver no Render → USA A DO RENDER
# Se NÃO estiver → usa o valor abaixo como reserva
DONO_ID = int(os.environ.get("DONO_ID", "7711945457"))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", "-1004399892914"))
MONGO_URI = os.environ.get("MONGO_URI")

# ✅ VÍDEOS DO /START
LISTA_VIDEOS_START = [
    "https://ellixgr.github.io/x23wzp/VN20260728_020021.mp4",
    "https://ellixgr.github.io/x23wzp/VN20260728_015729.mp4"
]

# ==============================================
# ✅ CONEXÃO BANCO
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
    print("✅ Conectado ao MongoDB!")
except Exception as e:
    print(f"❌ ERRO NO BANCO: {e}")

TEMPO_INICIAL = time.time()
ultimo_envio = {}
contador_spam = {}
usuarios_bloqueados = {}
bloqueio_temporario = {}
pagamentos_notificados = set()

# ==============================================
# ✅ INTERCEPTADOR — NÃO BLOQUEIA /START
# ==============================================
async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    agora = time.time()

    if user_id == DONO_ID:
        return

    # ✅ LIBERA /START SEMPRE — NÃO BLOQUEIA NUNCA!
    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        if cmd in ['/start', '/suporte', '/suport', '/id', '/ping']:
            pass
        else:
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
        if agora - ultimo_envio[user_id] < 0.4:
            contador_spam[user_id] = contador_spam.get(user_id, 0) + 1
            ultimo_envio[user_id] = agora
            if contador_spam[user_id] >= 15:
                bloqueio_temporario[user_id] = agora + 60
                contador_spam[user_id] = 0
                if update.effective_chat.type == "private":
                    try:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text="⚠️ Calma aí! Manda mais devagar 😅",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                raise ApplicationHandlerStop
            raise ApplicationHandlerStop

    ultimo_envio[user_id] = agora

# ==============================================
# ✅ SALVA GRUPOS
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
            elif new_status in ["left", "kicked"]:
                collection_chats.delete_one({"chat_id": chat.id})
        except Exception as e:
            print(f"Erro ao salvar chat: {e}")

# ==============================================
# ✅ /START — MOSTRA O ERRO NO CHAT!
# ==============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    texto_boas_vindas = (
        "🔥 **𝐴𝑄𝑈𝐼 𝑇𝐸𝑀 𝑇𝑂𝐷𝑂𝑆 𝑂𝑆 𝐶𝑂𝑁𝑇𝐸𝑈𝐷𝑂𝑆** 🇧🇷\n\n"
        "🤭🔥Tenha acesso completo a todo o nosso conteúdo atualizado em um só lugar:\n\n"
        "📁 +2𝑚𝑖𝑙 mídias disponíveis (vídeos e fotos)\n"
        "👇 Escolha o seu plano abaixo para liberar o seu acesso:\n\n"
        "💡 *Precisa de ajuda? Fale com o suporte:* @Lyhhxv"
    )

    keyboard = [
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐎𝐑 1 𝐃𝐈𝐀 → R$ 2,50 🔥", callback_data="comprar_2.50")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐎𝐑 1 𝐒𝐄𝐌𝐀𝐍𝐀 → R$ 7,00", callback_data="comprar_7.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐎𝐑 1 𝐌𝐄𝐒 → R$ 20,00", callback_data="comprar_20.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐄𝐑𝐌𝐀ℕ𝐄𝐍𝐓𝐄 → R$ 60,00", callback_data="comprar_60.00")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    video_escolhido = random.choice(LISTA_VIDEOS_START)

    try:
        await update.message.reply_video(
            video=video_escolhido,
            caption=texto_boas_vindas,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            protect_content=True,
            supports_streaming=True
        )
    except Exception as e:
        erro_msg = f"⚠️ Não foi possível carregar o vídeo:\n`{str(e)}`\n\nEnviando apenas o texto..."
        print(f"❌ ERRO AO ENVIAR VÍDEO: {e}")
        try:
            await update.message.reply_text(erro_msg, parse_mode="Markdown")
        except:
            pass
        await update.message.reply_text(texto_boas_vindas, reply_markup=reply_markup, parse_mode="Markdown")

# ==============================================
# ✅ COMANDOS DO DONO
# ==============================================
async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    chat = update.effective_chat
    user = update.effective_user
    resposta = (
        f"📊 **INFORMAÇÕES DE ID:**\n\n"
        f"💬 **Nome do Chat:** {chat.title if chat.title else 'Privado'}\n"
        f"🆔 **ID deste Chat/Grupo:** `{chat.id}`\n"
        f"👤 **Seu ID de Usuário:** `{user.id}`"
    )
    await update.message.reply_text(resposta, parse_mode="Markdown")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    inicio = time.time()
    msg = await update.message.reply_text("pong 🏓...")
    latencia = int((time.time() - inicio) * 1000)
    uptime = int(time.time() - TEMPO_INICIAL)
    resposta = (
        f"🏓 **PONG! Informações do Sistema:**\n\n"
        f"⚡ **Latência do Bot:** `{latencia}ms`\n"
        f"⏳ **Uptime:** `{uptime // 3600}h {(uptime % 3600) // 60}m {uptime % 60}s`\n"
        f"🧠 **Memória RAM:** `512 MB (Render Cloud)`"
    )
    await msg.edit_text(resposta, parse_mode="Markdown")

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 **Central de Suporte**\n\n"
        "Para tirar dúvidas ou resolver qualquer problema, entre em contato diretamente com o nosso suporte:\n\n"
        "👉 **@Lyhhxv**",
        parse_mode="Markdown"
    )

async def addusuario_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ Use corretamente:\n"
            "• `/addusuario <id> plano 2 / 50m` (minutos)\n"
            "• `/addusuario <id> plano 2 / 2h` (horas)\n"
            "• `/addusuario <id> plano 2 / 3d` (dias)\n"
            "• `/addusuario <id> plano 7` (dias padrão)",
            parse_mode="Markdown"
        )
        return
    try:
        user_id = int(args[0])
        resto_texto = "".join(args[1:]).lower()
        duracao_segundos = 86400
        tempo_str_formatado = ""
        match_m = re.search(r'(\d+)m', resto_texto)
        match_h = re.search(r'(\d+)h', resto_texto)
        match_d = re.search(r'(\d+)d', resto_texto)
        if match_m:
            qtd_minutos = int(match_m.group(1))
            duracao_segundos = qtd_minutos * 60
            tempo_str_formatado = f"{qtd_minutos} minuto(s)"
        elif match_h:
            qtd_horas = int(match_h.group(1))
            duracao_segundos = qtd_horas * 3600
            tempo_str_formatado = f"{qtd_horas} hora(s)"
        elif match_d:
            qtd_dias = int(match_d.group(1))
            duracao_segundos = qtd_dias * 86400
            tempo_str_formatado = f"{qtd_dias} dia(s)"
        else:
            plano_arg = args[1].lower()
            if plano_arg.startswith("plano"):
                if len(args) < 3:
                    await update.message.reply_text("⚠️ Informe o valor do plano. Ex: `/addusuario 837382929 plano 2`", parse_mode="Markdown")
                    return
                dias_valor = int(re.sub(r'[^0-9]', '', args[2]) or '1')
            else:
                dias_valor = int(re.sub(r'[^0-9]', '', plano_arg) or '1')
            if dias_valor == 7:
                duracao_segundos = 86400 * 7
            elif dias_valor == 20:
                duracao_segundos = 86400 * 30
            elif dias_valor == 60:
                duracao_segundos = 86400 * 365 * 10
            elif dias_valor == 2:
                duracao_segundos = 86400 * 1
            else:
                duracao_segundos = 86400 * dias_valor
            tempo_str_formatado = f"{dias_valor} dia(s)"
        tempo_expiracao = time.time() + duracao_segundos
        collection_clientes.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "nome": "Adicionado Manualmente", "expira_em": tempo_expiracao, "aviso_1dia_enviado": False, "aviso_20min_enviado": False}},
            upsert=True
        )
        await update.message.reply_text(f"✅ Usuário `{user_id}` adicionado com sucesso por `{tempo_str_formatado}`!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao adicionar usuário: {e}")

async def delusuario_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Use: `/delusuario <id_usuario>`", parse_mode="Markdown")
        return
    try:
        user_id = int(args[0])
        resultado = collection_clientes.delete_one({"user_id": user_id})
        if resultado.deleted_count > 0:
            await update.message.reply_text(f"✅ O usuário `{user_id}` foi removido da lista de clientes com sucesso!", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ O usuário `{user_id}` não foi encontrado na base de dados.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao remover usuário: {e}")

# ==============================================
# ✅ PAGAMENTO MERCADO PAGO
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
            qr = dados.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")
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
    except Exception as e:
        print(f"❌ ERRO AO CONSULTAR PAGAMENTO: {e}")
        return False, 0

# ==============================================
# ✅ BOTÕES E PAGAMENTO
# ==============================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    dados = query.data

    if dados.startswith("comprar_"):
        valor = float(dados.split("_")[1])
        try:
            await query.edit_message_text("⏳ Gerando seu PIX, aguarde um instante...")
        except:
            pass
        user = update.effective_user
        ok, pag_id, qr = await gerar_pagamento(valor, user, context.bot)
        if ok:
            msg_completa = (
                f"✅ **PIX Gerado com Sucesso!**\n\n"
                f"💰 **Valor:** R$ {valor:.2f}\n\n"
                f"📋 **Código Pix Copia e Cola:**\n`{qr}`"
            )
            keyboard_final = [
                [InlineKeyboardButton("📋 Copiar Código Pix", copy_text=qr)],
                [InlineKeyboardButton("🔄 Verificar Pagamento", callback_data=f"check_{pag_id}")]
            ]
            await query.message.reply_text(msg_completa, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard_final))
        else:
            await query.message.reply_text(f"❌ Erro ao gerar o Pix:\n{qr}", parse_mode="Markdown")

    elif dados.startswith("check_"):
        payment_id = dados.split("_")[1]
        aprovado, valor_pago = await verificar_pagamento(payment_id)
        if aprovado:
            try:
                await query.answer("🎉 Pagamento Aprovado!", show_alert=True)
            except:
                pass
            if valor_pago == 2.50:
                duracao_segundos = 86400
                nome_plano = "1 Dia 🔥"
            elif valor_pago == 7.00:
                duracao_segundos = 86400 * 7
                nome_plano = "1 Semana"
            elif valor_pago == 20.00:
                duracao_segundos = 86400 * 30
                nome_plano = "1 Mês"
            elif valor_pago == 60.00:
                duracao_segundos = 86400 * 365 * 10
                nome_plano = "Permanente"
            else:
                duracao_segundos = int(valor_pago) * 86400
                nome_plano = f"Personalizado R$ {valor_pago:.2f}"
            user_id = update.effective_user.id
            tempo_expiracao = time.time() + duracao_segundos
            collection_clientes.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "nome": update.effective_user.first_name or "Cliente", "expira_em": tempo_expiracao, "aviso_1dia_enviado": False, "aviso_20min_enviado": False}},
                upsert=True
            )
            link_convite = None
            if CANAL_ALVO_ID != 0:
                try:
                    convite = await context.bot.create_chat_invite_link(chat_id=CANAL_ALVO_ID, member_limit=1, expire_date=int(time.time()) + 86400)
                    link_convite = convite.invite_link
                except Exception as e:
                    print(f"⚠️ Erro ao gerar link: {e}")
            texto_link = f"Aqui está o seu link de acesso exclusivo:\n{link_convite}" if link_convite else "⚠️ Entre em contato com o suporte (@Lyhhxv) para liberar seu acesso."
            await query.message.reply_text(
                f"🎉 **Pagamento Aprovado com Sucesso!**\n\n✅ Plano: **{nome_plano}**\n💰 Valor: **R$ {valor_pago:.2f}**\n\nMuito obrigado pela compra!\n{texto_link}",
                parse_mode="Markdown"
            )
            if payment_id not in pagamentos_notificados:
                pagamentos_notificados.add(payment_id)
                comprador = update.effective_user
                relatorio = (
                    f"🚨 **NOVA ASSINATURA CONFIRMADA!** 🚨\n\n"
                    f"👤 **Cliente:** {comprador.first_name or 'Sem nome'}\n"
                    f"🔗 **Username:** @{comprador.username if comprador.username else 'Sem @'}\n"
                    f"🆔 **ID do Telegram:** `{comprador.id}`\n"
                    f"💰 **Valor Pago:** R$ {valor_pago:.2f}\n"
                    f"📅 **Plano Escolhido:** {nome_plano}\n"
                    f"⏰ **Data/Hora:** {time.strftime('%d/%m/%Y às %H:%M:%S', time.localtime())}\n"
                    f"🧾 **ID do Pix:** `{payment_id}`\n🟢 **Status:** Aprovado"
                )
                try:
                    await context.bot.send_message(chat_id=DONO_ID, text=relatorio, parse_mode="Markdown")
                except:
                    pass
        else:
            try:
                await query.answer("❌ Pagamento ainda não identificado!", show_alert=True)
            except:
                pass
            await query.message.reply_text(
                "⏳ **Pagamento ainda não identificado!**\n\nRealize o pagamento no app do seu banco via Pix Copia e Cola. Se já pagou, aguarde alguns segundos e clique novamente.",
                parse_mode="Markdown"
            )

    elif dados == "renovar_2.50":
        query.data = "comprar_2.50"
        await button_handler(update, context)

    elif dados == "ver_outros_precos":
        keyboard = [
            [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐎𝐑 1 𝐒𝐄𝐌𝐀𝐍𝐀 → R$ 7,00", callback_data="comprar_7.00")],
            [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐎𝐑 1 𝐌𝐄𝐒 → R$ 20,00", callback_data="comprar_20.00")],
            [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐄𝐑𝐌𝐀ℕ𝐄𝐍𝐓𝐄 → R$ 60,00", callback_data="comprar_60.00")]
        ]
        await query.message.reply_text("Escolha outro plano abaixo:", reply_markup=InlineKeyboardMarkup(keyboard))

# ==============================================
# ✅ GERENCIADOR DE ASSINATURAS
# ==============================================
async def gerenciador_assinaturas(application):
    await asyncio.sleep(10)
    while True:
        try:
            agora = time.time()
            for cliente in collection_clientes.find():
                user_id = cliente["user_id"]
                expira_em = cliente["expira_em"]
                tempo_restante = expira_em - agora
                if 82800 <= tempo_restante <= 86400 and not cliente.get("aviso_1dia_enviado", False):
                    try:
                        msg = "⚠️ **SEU PLANO VENCE AMANHÃ!** ⚠️\n\nO seu acesso expira em breve! Renove para não perder o conteúdo!\n\n👇 Escolha abaixo:"
                        keyboard = [
                            [InlineKeyboardButton("🔄 Renovar R$ 2,50 (1 Dia)", callback_data="renovar_2.50")],
                            [InlineKeyboardButton("💎 Ver Outros Planos", callback_data="ver_outros_precos")]
                        ]
                        await application.bot.send_message(chat_id=user_id, text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                        collection_clientes.update_one({"user_id": user_id}, {"$set": {"aviso_1dia_enviado": True}})
                    except:
                        pass
                elif 0 < tempo_restante <= 1200 and not cliente.get("aviso_20min_enviado", False):
                    try:
                        msg = "🚨 **SEU PLANO EXPIRA EM POUCOS MINUTOS!** 🚨\n\nGaranta sua permanência agora!\n👇 Pague abaixo:"
                        keyboard = [
                            [InlineKeyboardButton("🔄 Renovar R$ 2,50", callback_data="renovar_2.50")],
                            [InlineKeyboardButton("📋 Ver Outros Preços", callback_data="ver_outros_precos")]
                        ]
                        await application.bot.send_message(chat_id=user_id, text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                        collection_clientes.update_one({"user_id": user_id}, {"$set": {"aviso_20min_enviado": True}})
                    except:
                        pass
                elif tempo_restante <= 0 and CANAL_ALVO_ID != 0:
                    try:
                        await application.bot.ban_chat_member(chat_id=CANAL_ALVO_ID, user_id=user_id)
                        await application.bot.unban_chat_member(chat_id=CANAL_ALVO_ID, user_id=user_id)
                        await application.bot.send_message(chat_id=user_id, text="❌ **Seu plano expirou e você foi removido do canal.**\n\nDigite /start para comprar novamente!", parse_mode="Markdown")
                    except:
                        pass
                    collection_clientes.delete_one({"user_id": user_id})
        except Exception as e:
            print(f"Erro no gerenciador: {e}")
        await asyncio.sleep(60)

def run_background_loop(application):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(gerenciador_assinaturas(application))

# ==============================================
# ✅ INÍCIO
# ==============================================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    threading.Thread(target=run_background_loop, args=(app,), daemon=True).start()
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
