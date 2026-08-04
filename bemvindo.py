import os
import logging
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

logger = logging.getLogger("SanizinhaBot.BemVindo")

# ✅ DADOS DO SEU BOT
DONO_ID = int(os.getenv("DONO_ID", "7711945457"))
LINK_BOT = "https://t.me/Aninhaxv1bot"

MONGO_URI = os.getenv("MONGO_URI")
from pymongo import MongoClient
mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
db = mongo_client["sanizinhabot_db"]
col_bemvindo = db["config_bem_vindo"]

FUSO_BR = timezone(timedelta(hours=-3))
ESTADOS_FLUXO = {}

# ✅ TEXTO DE BOAS-VINDAS EXATO QUE VOCÊ PEDIU
TEXTO_BEMVINDO = """👇🏻𝐓𝐄𝐍𝐇𝐀 𝐀𝐂𝐄𝐒𝐒𝐎 𝐀𝐎 𝐆𝐑𝐔𝐏𝐎 𝐕𝐈P💎

♦️ 𝗔𝗰𝗲𝘀𝘀𝗼 𝗮 𝗺𝗶𝗹𝗵𝗮𝗿𝗲𝘀 𝗱𝗲 𝗰𝗼𝗻𝘁𝗲𝘂‌𝗱𝗼𝘀
🔐 +2𝟬𝟬0 𝗠𝗜𝗟 𝗠𝗜𝗗𝗜𝗔𝗦 𝗟𝗜𝗕𝗘𝗥𝗔𝗗𝗔𝗦
🔥 𝗖𝗼𝗻𝘁𝗲𝘂‌𝗱𝗼𝘀 𝗾𝘂𝗲 𝘃𝗶𝗿𝗮𝗹𝗶𝘇𝗮𝗺 𝗲 𝘀𝘂𝗺𝗲𝗺 𝗱𝗮 𝗶𝗻𝘁𝗲𝗿𝗻𝗲𝘁
💀 𝗠𝗶𝗱𝗶𝗮𝘀 𝗿𝗮𝗿𝗮𝘀 𝗲 𝗱𝗶𝗳𝗶‌𝗰𝗲𝗶𝘀 𝗱𝗲 𝗲𝗻𝗰𝗼𝗻𝘁𝗿𝗮𝗿
💋 𝗙𝗮𝗺𝗼𝘀𝗮𝘀 / 𝗣𝗿𝗶𝘃𝗮𝗰𝘆 / 𝗢𝗻𝗹𝘆𝗙𝗮𝗻𝘀
🫦 𝗘𝘅𝗰𝗹𝘂𝘀𝗶𝘃𝗼𝘀 𝘀𝗲𝗹𝗲𝗰𝗶𝗼𝗻𝗮𝗱𝗼𝘀"""

# ✅ VERIFICA SE É O DONO
async def eh_dono(user_id: int) -> bool:
    return str(user_id) == str(DONO_ID)

# ✅ CARREGA DADOS SALVOS
def carregar_dados_bv(chat_id: int):
    doc = col_bemvindo.find_one({"chat_id": chat_id})
    if not doc:
        return None, True
    texto = doc.get("texto")
    status = doc.get("status", True)
    return texto, status

# ✅ SALVA NO BANCO
def salvar_bv(chat_id: int, campo: str, valor):
    col_bemvindo.update_one({"chat_id": chat_id}, {"$set": {campo: valor}}, upsert=True)

def alternar_status(chat_id: int) -> bool:
    doc = col_bemvindo.find_one({"chat_id": chat_id})
    status_atual = doc.get("status", True) if doc else True
    novo = not status_atual
    salvar_bv(chat_id, "status", novo)
    return novo

# ✅ === COMANDO /bemvindo ===
async def cmd_bemvindo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_tipo = update.effective_chat.type

    if not await eh_dono(user_id):
        return

    if chat_tipo != "private":
        await update.message.reply_text("⚠️ Use este comando aqui no privado do bot!")
        return

    await listar_grupos_para_escolher(update, context)

# ✅ LISTA OS GRUPOS CADASTRADOS
async def listar_grupos_para_escolher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from pymongo import MongoClient
    MONGO_URI = os.getenv("MONGO_URI")
    mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
    db_chats = mongo["sanizinhabot_db"]["chats_autorizados"]

    chats = list(db_chats.find({}))
    if not chats:
        await update.message.reply_text(
            "❌ Nenhum grupo encontrado!\nAdicione o bot em um grupo primeiro.",
            parse_mode="Markdown"
        )
        return

    teclado = []
    for c in chats:
        cid = c.get("chat_id")
        nome = c.get("title", f"Grupo {cid}")
        teclado.append([InlineKeyboardButton(f"👥 {nome}", callback_data=f"bv_config_{cid}")])

    await update.message.reply_text(
        "🎛 **PAINEL DE BOAS-VINDAS**\n\n"
        "Escolha abaixo qual grupo você quer configurar:",
        reply_markup=InlineKeyboardMarkup(teclado),
        parse_mode="Markdown"
    )

# ✅ === ABRE PAINEL DO GRUPO ===
async def abrir_painel_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_alvo_id, msg_ref=None):
    texto, status = carregar_dados_bv(chat_alvo_id)
    status_emoji = "🟢 Ativado" if status else "🔴 Desativado"
    tem_texto = "✅" if texto else "❌"

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Editar Texto", callback_data=f"bv_edtxt_{chat_alvo_id}"),
         InlineKeyboardButton("👀 Ver Texto", callback_data=f"bv_vertxt_{chat_alvo_id}")],
        [InlineKeyboardButton("🟢 Ativar" if not status else "🔴 Desativar", callback_data=f"bv_toggle_{chat_alvo_id}")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="bv_voltar")]
    ])

    msg_texto = (
        f"🎛 **Boas-Vindas — Grupo: `{chat_alvo_id}`**\n\n"
        f"Status: {status_emoji}\n"
        f"Texto personalizado: {tem_texto}"
    )

    if msg_ref:
        await msg_ref.edit_text(msg_texto, reply_markup=teclado, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(msg_texto, reply_markup=teclado, parse_mode="Markdown")

# ✅ === ENVIA BOAS-VINDAS — SÓ TEXTO + BOTÃO ===
async def enviar_bemvindo(chat_id_destino, context: ContextTypes.DEFAULT_TYPE):
    """Envia só o texto + botão — sem tentar pegar mídia nenhuma"""
    texto_personalizado, _ = carregar_dados_bv(chat_id_destino)
    texto_final = texto_personalizado if texto_personalizado else TEXTO_BEMVINDO

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 ACESSAR CONTEÚDO 💎", url=LINK_BOT)]
    ])

    await context.bot.send_message(
        chat_id_destino,
        texto_final,
        reply_markup=teclado,
        parse_mode="Markdown"
    )

# ✅ === QUANDO ALGUÉM ENTRA NO GRUPO ===
async def novo_membro_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    chat_id = update.effective_chat.id
    _, status = carregar_dados_bv(chat_id)
    if not status:
        return

    for membro in update.message.new_chat_members:
        if membro.is_bot:
            continue
        await enviar_bemvindo(chat_id, context)

# ✅ === TRATA TODOS OS BOTÕES ===
async def botoes_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dados = query.data
    user_id = update.effective_user.id

    if not await eh_dono(user_id):
        await query.answer("❌ Apenas o dono!", show_alert=True)
        return

    if dados.startswith("bv_config_"):
        gid = int(dados.replace("bv_config_", ""))
        await abrir_painel_grupo(update, context, gid)

    elif dados.startswith("bv_toggle_"):
        gid = int(dados.replace("bv_toggle_", ""))
        alternar_status(gid)
        await abrir_painel_grupo(update, context, gid)

    elif dados.startswith("bv_edtxt_"):
        gid = int(dados.replace("bv_edtxt_", ""))
        ESTADOS_FLUXO[(update.effective_chat.id, user_id)] = ("bv_texto", gid)
        await query.message.edit_text(
            "📝 **Agora envie o texto de boas-vindas que deseja usar!**\n\n"
            "Você pode usar:\n"
            "{NAME} = nome do usuário\n"
            "{MENTION} = menção ao usuário\n"
            "{DATE} = data de entrada\n"
            "{GROUPNAME} = nome do grupo",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancelar", callback_data="bv_cancelar")]]),
            parse_mode="Markdown"
        )

    elif dados.startswith("bv_vertxt_"):
        gid = int(dados.replace("bv_vertxt_", ""))
        texto, _ = carregar_dados_bv(gid)
        txt = texto or TEXTO_BEMVINDO
        await query.message.edit_text(
            f"📄 **Texto atual:**\n\n{txt}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data=f"bv_config_{gid}")]]),
            parse_mode="Markdown"
        )

    elif dados == "bv_voltar":
        await listar_grupos_para_escolher(update, context)

    elif dados == "bv_cancelar":
        ESTADOS_FLUXO.pop((update.effective_chat.id, user_id), None)
        await listar_grupos_para_escolher(update, context)

# ✅ === RECEBE O TEXTO PERSONALIZADO ===
async def capturar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cid = update.effective_chat.id
    chave = (cid, uid)

    if chave not in ESTADOS_FLUXO:
        return

    estado, gid = ESTADOS_FLUXO.pop(chave)
    if estado == "bv_texto":
        texto = update.message.text or update.message.caption or ""
        salvar_bv(gid, "texto", texto)
        await update.message.reply_text("✅ **TEXTO SALVO COM SUCESSO!** ✅", parse_mode="Markdown")
        await abrir_painel_grupo(update, context, gid)

# ✅ === REGISTRAR NO BOT PRINCIPAL ===
def registrar_bemvindo(application):
    application.add_handler(CommandHandler("bemvindo", cmd_bemvindo))
    application.add_handler(CallbackQueryHandler(botoes_painel, pattern=r"^bv_"))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        capturar_texto
    ))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS & ~filters.ChatType.PRIVATE,
        novo_membro_handler
    ))
