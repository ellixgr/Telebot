import os
import logging
import random
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
GRUPO_MIDIAS_ID = -1004399892914  # ← Grupo de onde pega as mídias
LINK_BOT = "https://t.me/Aninhaxv1bot"

MONGO_URI = os.getenv("MONGO_URI")
from pymongo import MongoClient
mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
db = mongo_client["sanizinhabot_db"]
col_bemvindo = db["config_bem_vindo"]

FUSO_BR = timezone(timedelta(hours=-3))
ESTADOS_FLUXO = {}

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

# ✅ === COMANDO /bemvindo — SÓ FUNCIONA NO PRIVADO E SÓ P/ O DONO ===
async def cmd_bemvindo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_tipo = update.effective_chat.type

    # ❌ Ignora se não for o dono
    if not await eh_dono(user_id):
        return

    # ❌ Ignora se for no grupo → só funciona no privado
    if chat_tipo != "private":
        await update.message.reply_text("⚠️ Use este comando aqui no privado do bot!")
        return

    await listar_grupos_para_escolher(update, context)


# ✅ LISTA OS GRUPOS CADASTRADOS PARA O DONO ESCOLHER
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


# ✅ === ABRE PAINEL DO GRUPO ESCOLHIDO ===
async def abrir_painel_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_alvo_id, msg_ref=None):
    texto, status = carregar_dados_bv(chat_alvo_id)
    status_emoji = "🟢 Ativado" if status else "🔴 Desativado"
    tem_texto = "✅" if texto else "❌"

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Editar Texto", callback_data=f"bv_edtxt_{chat_alvo_id}"),
         InlineKeyboardButton("👀 Ver Texto", callback_data=f"bv_vertxt_{chat_alvo_id}")],
        [InlineKeyboardButton("⚡ BOAS-VINDAS RÁPIDAS", callback_data=f"bv_rapida_{chat_alvo_id}")],
        [InlineKeyboardButton("🟢 Ativar" if not status else "🔴 Desativar", callback_data=f"bv_toggle_{chat_alvo_id}")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="bv_voltar")]
    ])

    msg_texto = (
        f"🎛 **Boas-Vindas — Grupo: `{chat_alvo_id}`**\n\n"
        f"Status: {status_emoji}\n"
        f"Texto personalizado: {tem_texto}\n\n"
        f"⚡ **Boas-Vindas Rápidas** = Envia mídia aleatória + botão → {LINK_BOT}"
    )

    if msg_ref:
        await msg_ref.edit_text(msg_texto, reply_markup=teclado, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(msg_texto, reply_markup=teclado, parse_mode="Markdown")


# ✅ === BOAS-VINDAS RÁPIDAS — PEGA MÍDIA ALEATÓRIA DO GRUPO E MANDA ===
async def boas_vindas_rapidas(chat_id_novo_membro, context: ContextTypes.DEFAULT_TYPE):
    """Executado automaticamente quando alguém entra"""
    texto_padrao = (
        "🎉 **SEJA BEM-VINDO(A)!** 🎉\n\n"
        "Ficamos muito felizes em ter você aqui! 💖\n"
        "Clique no botão abaixo para acessar tudo:"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 ACESSAR CONTEÚDO 💎", url=LINK_BOT)]
    ])

    # ✅ PEGA MÍDIA ALEATÓRIA DO GRUPO DE MÍDIAS (até 2MB)
    midia_escolhida = await buscar_midia_aleatoria(context)

    try:
        if midia_escolhida:
            tipo, file_id = midia_escolhida
            if tipo == "photo":
                await context.bot.send_photo(
                    chat_id_novo_membro,
                    file_id,
                    caption=texto_padrao,
                    reply_markup=teclado,
                    parse_mode="Markdown"
                )
            elif tipo == "video":
                await context.bot.send_video(
                    chat_id_novo_membro,
                    file_id,
                    caption=texto_padrao,
                    reply_markup=teclado,
                    parse_mode="Markdown"
                )
        else:
            await context.bot.send_message(
                chat_id_novo_membro,
                texto_padrao,
                reply_markup=teclado,
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Erro ao enviar boas-vindas: {e}")
        try:
            await context.bot.send_message(chat_id_novo_membro, texto_padrao, reply_markup=teclado, parse_mode="Markdown")
        except:
            pass


# ✅ BUSCA MÍDIA ALEATÓRIA NO GRUPO DE MÍDIAS (até 2MB)
async def buscar_midia_aleatoria(context: ContextTypes.DEFAULT_TYPE):
    try:
        midias_validas = []
        async for msg in context.bot.get_chat_history(GRUPO_MIDIAS_ID, limit=150):
            if msg.photo:
                foto = msg.photo[-1]
                tamanho_mb = (foto.file_size or 0) / 1048576
                if tamanho_mb <= 2.0:
                    midias_validas.append(("photo", foto.file_id))
            elif msg.video and not msg.video.is_animation:
                tamanho_mb = (msg.video.file_size or 0) / 1048576
                if tamanho_mb <= 2.0:
                    midias_validas.append(("video", msg.video.file_id))
            if len(midias_validas) >= 20:
                break

        if midias_validas:
            return random.choice(midias_validas)
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar mídias: {e}")
        return None


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
        await boas_vindas_rapidas(chat_id, context)


# ✅ === TRATA TODOS OS BOTÕES DO PAINEL ===
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
        novo = alternar_status(gid)
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
        txt = texto or "⚠️ Nenhum texto personalizado salvo."
        await query.message.edit_text(
            f"📄 **Texto atual:**\n\n{txt}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data=f"bv_config_{gid}")]]),
            parse_mode="Markdown"
        )

    elif dados.startswith("bv_rapida_"):
        gid = int(dados.replace("bv_rapida_", ""))
        salvar_bv(gid, "modo_rapido", True)
        await query.message.edit_text(
            "✅ **BOAS-VINDAS RÁPIDAS ATIVADAS!** ⚡\n\n"
            "Quando alguém entrar:\n"
            "📸 Pega 1 foto/vídeo ALEATÓRIO (até 2MB) do grupo de mídias\n"
            "💎 Envia com botão → " + LINK_BOT + "\n\n"
            "Pronto! É só isso!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data=f"bv_config_{gid}")]]),
            parse_mode="Markdown"
        )

    elif dados == "bv_voltar":
        await listar_grupos_para_escolher(update, context)

    elif dados == "bv_cancelar":
        ESTADOS_FLUXO.pop((update.effective_chat.id, user_id), None)
        await listar_grupos_para_escolher(update, context)


# ✅ === RECEBE O TEXTO QUE O DONO ENVIOU ===
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
        salvar_bv(gid, "modo_rapido", False)
        await update.message.reply_text("✅ **TEXTO SALVO COM SUCESSO!** ✅", parse_mode="Markdown")
        await abrir_painel_grupo(update, context, gid)


# ✅ === FUNÇÃO PARA REGISTRAR TUDO NO BOT PRINCIPAL ===
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
