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
from pymongo import MongoClient

logger = logging.getLogger("SanizinhaBot.BemVindo")

DONO_ID = int(os.getenv("DONO_ID", "7711945457"))
MONGO_URI = os.getenv("MONGO_URI")
LINK_BOT_PADRAO = "https://t.me/Aninhaxv1bot"

mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
db = mongo_client["sanizinhabot_db"]
col_bemvindo = db["config_bem_vindo"]

FUSO_BR = timezone(timedelta(hours=-3))
ESTADOS_FLUXO = {}

TEXTO_PADRAO = """👇🏻𝐓𝐄𝐍𝐇𝐀 𝐀𝐂𝐄𝐒𝐒𝐎 𝐀𝐎 𝐆𝐑𝐔𝐏𝐎 𝐕𝐈P💎

♦️ 𝗔𝗰𝗲𝘀𝘀𝗼 𝗮 𝗺𝗶𝗹𝗵𝗮𝗿𝗲𝘀 𝗱𝗲 𝗰𝗼𝗻𝘁𝗲𝘂‌𝗱𝗼𝘀
🔐 +2𝟬𝟬0 𝗠𝗜𝗟 𝗠𝗜𝗗𝗜𝗔𝗦 𝗟𝗜𝗕𝗘𝗥𝗔𝗗𝗔𝗦
🔥 𝗖𝗼𝗻𝘁𝗲𝘂‌𝗱𝗼𝘀 𝗾𝘂𝗲 𝘃𝗶𝗿𝗮𝗹𝗶𝘇𝗮𝗺 𝗲 𝘀𝘂𝗺𝗲𝗺 𝗱𝗮 𝗶𝗻𝘁𝗲𝗿𝗻𝗲𝘁
💀 𝗠𝗶𝗱𝗶𝗮𝘀 𝗿𝗮𝗿𝗮𝘀 𝗲 𝗱𝗶𝗳𝗶‌𝗰𝗲𝗶𝘀 𝗱𝗲 𝗲𝗻𝗰𝗼𝗻𝘁𝗿𝗮𝗿
💋 𝗙𝗮𝗺𝗼𝘀𝗮𝘀 / 𝗣𝗿𝗶𝘃𝗮𝗰𝘆 / 𝗢𝗻𝗹𝘆𝗙𝗮𝗻𝘀
🫦 𝗘𝘅𝗰𝗹𝘂𝘀𝗶𝘃𝗼𝘀 𝘀𝗲𝗹𝗲𝗰𝗶𝗼𝗻𝗮𝗱𝗼𝘀"""

async def eh_dono_ou_adm(user_id: int) -> bool:
    return str(user_id) == str(DONO_ID)

# ✅ CARREGA DADOS — PADRÃO = DESATIVADO
def carregar_dados_bv(chat_id: int):
    doc = col_bemvindo.find_one({"chat_id": chat_id})
    if not doc:
        return None, None, None, False
    texto = doc.get("texto")
    midia = doc.get("midia")
    if midia:
        midia = tuple(midia)
    botoes_raw = doc.get("botoes")
    botoes = None
    if botoes_raw:
        teclado = []
        for linha in botoes_raw:
            linha_botoes = []
            for b in linha:
                if "url" in b:
                    linha_botoes.append(InlineKeyboardButton(b["text"], url=b["url"]))
            teclado.append(linha_botoes)
        botoes = InlineKeyboardMarkup(teclado)
    status = doc.get("status", False)
    return texto, midia, botoes, status

def salvar_bv(chat_id: int, campo: str, valor):
    if campo == "botoes" and isinstance(valor, InlineKeyboardMarkup):
        serial = []
        for linha in valor.inline_keyboard:
            linha_s = []
            for b in linha:
                item = {"text": b.text}
                if b.url:
                    item["url"] = b.url
                linha_s.append(item)
            serial.append(linha_s)
        valor = serial
    col_bemvindo.update_one({"chat_id": chat_id}, {"$set": {campo: valor}}, upsert=True)

# ✅ ALTERNA E RETORNA O STATUS NOVO
def alternar_status(chat_id: int) -> bool:
    doc = col_bemvindo.find_one({"chat_id": chat_id})
    status_atual = doc.get("status", False) if doc else False
    novo = not status_atual
    salvar_bv(chat_id, "status", novo)
    return novo

async def formatar_texto(chat_id: int, usuario, context: ContextTypes.DEFAULT_TYPE):
    texto_base, _, _, _ = carregar_dados_bv(chat_id)
    if not texto_base:
        texto_base = TEXTO_PADRAO

    agora = datetime.now(FUSO_BR)
    dia_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"][agora.weekday()]
    
    nome = usuario.first_name or "Usuário"
    mencao = usuario.mention_html()
    username = f"@{usuario.username}" if usuario.username else "SemUsuario"
    
    try:
        grupo = await context.bot.get_chat(chat_id)
        nome_grupo = grupo.title or "Grupo"
    except:
        nome_grupo = "Grupo"

    substituicoes = {
        "{NAME}": nome,
        "{MENTION}": mencao,
        "{DATE}": agora.strftime("%d/%m/%Y"),
        "{TIME}": agora.strftime("%H:%M"),
        "{WEEKDAY}": dia_semana,
        "{USERNAME}": username,
        "{GROUPNAME}": nome_grupo,
        "{ID}": str(usuario.id)
    }
    for chave, val in substituicoes.items():
        texto_base = texto_base.replace(chave, val)
    return texto_base

# ✅ ENVIA BOAS-VINDAS — SÓ SE ESTIVER ATIVADO
async def enviar_bemvindo_membro(chat_id: int, usuario, context: ContextTypes.DEFAULT_TYPE):
    _, midia, botoes, status = carregar_dados_bv(chat_id)
    
    if not status:
        return

    texto_final = await formatar_texto(chat_id, usuario, context)
    
    if not botoes:
        botoes = InlineKeyboardMarkup([[InlineKeyboardButton("💎 ACESSAR CONTEÚDO 💎", url=LINK_BOT_PADRAO)]])

    try:
        if midia:
            tipo, file_id, legenda = midia
            legenda_completa = f"{legenda}\n\n{texto_final}" if legenda else texto_final
            
            if tipo == "photo":
                await context.bot.send_photo(chat_id, file_id, caption=legenda_completa, reply_markup=botoes, parse_mode="HTML")
            elif tipo == "video":
                await context.bot.send_video(chat_id, file_id, caption=legenda_completa, reply_markup=botoes, parse_mode="HTML", supports_streaming=True)
            elif tipo == "sticker":
                await context.bot.send_sticker(chat_id, file_id)
                await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro ao enviar boas-vindas: {e}")
        try:
            await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
        except:
            pass

# ✅ QUANDO ALGUÉM ENTRA — CORRIGIDO O HANDLER
async def novo_membro_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ FUNCIONA NOS DOIS TIPOS DE GRUPO
    if not update.message:
        return
    novos_membros = update.message.new_chat_members
    if not novos_membros:
        return
    
    chat_id = update.effective_chat.id
    for membro in novos_membros:
        if membro.is_bot:
            continue
        await enviar_bemvindo_membro(chat_id, membro, context)

# ✅ PAINEL PRINCIPAL COM BOTÃO CERTO
async def painel_principal(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, msg_ref=None, aviso=""):
    texto, midia, botoes, status = carregar_dados_bv(chat_id)
    status_emoji = "🟢 Ativado" if status else "🔴 Desativado"
    tem_texto = "✅" if texto else "❌ (usará padrão)"
    tem_midia = "✅" if midia else "❌"
    tem_botao = "✅" if botoes else "❌ (usará padrão)"

    # ✅ BOTÃO MUDAA CONFORME STATUS — AGORA CERTO!
    texto_botao_status = "🔴 Desativar" if status else "🟢 Ativar"

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Editar Texto", callback_data="bv_edtxt"),
         InlineKeyboardButton("👀 Ver Texto", callback_data="bv_vertxt")],
        [InlineKeyboardButton("🎞️ Adicionar Mídia", callback_data="bv_edmidia"),
         InlineKeyboardButton("👀 Ver Mídia", callback_data="bv_vermidia")],
        [InlineKeyboardButton("🔲 Editar Botão URL", callback_data="bv_edbotao"),
         InlineKeyboardButton("👀 Ver Botão", callback_data="bv_verbotao")],
        [InlineKeyboardButton(texto_botao_status, callback_data="bv_toggle")]
    ])

    mensagem = (
        f"{aviso}"
        f"🎛 **BOAS-VINDAS — CONFIGURAÇÕES**\n\n"
        f"Status: {status_emoji}\n"
        f"📄 Texto: {tem_texto}\n"
        f"🎞️ Mídia: {tem_midia}\n"
        f"🔲 Botão: {tem_botao}\n\n"
        f"⚠️ Se estiver 🔴 Desativado → NÃO ENVIA NADA!\n\n"
        f"Escolha abaixo o que quer configurar:"
    )

    if msg_ref:
        await msg_ref.edit_text(mensagem, reply_markup=teclado, parse_mode="Markdown")
    else:
        await update.message.reply_text(mensagem, reply_markup=teclado, parse_mode="Markdown")

async def cmd_bemvindo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_tipo = update.effective_chat.type

    if not await eh_dono_ou_adm(user_id):
        return

    if chat_tipo != "private":
        await update.message.reply_text("⚠️ Use este comando aqui no privado do bot!")
        return

    await painel_principal(update, context, update.effective_chat.id)

# ✅ TRATA BOTÕES — CONSERTADO O STATUS
async def botoes_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dados = query.data
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await eh_dono_ou_adm(user_id):
        await query.answer("❌ Apenas o dono!", show_alert=True)
        return

    if dados == "bv_toggle":
        # ✅ MUDA O STATUS E RECARREGA ANTES DE MOSTRAR
        novo_status = alternar_status(chat_id)
        aviso = "✅ **ATIVADO!** Agora vai enviar!" if novo_status else "🔴 **DESATIVADO!** Não vai enviar mais nada!"
        await painel_principal(update, context, chat_id, msg_ref=query.message, aviso=aviso)

    elif dados == "bv_edtxt":
        ESTADOS_FLUXO[(chat_id, user_id)] = "aguardando_texto"
        await query.message.edit_text(
            "📝 **Agora envie o texto de boas-vindas!**\n\n"
            "Você pode usar:\n"
            "{NAME} = nome da pessoa\n"
            "{MENTION} = menção\n"
            "{DATE} = data\n"
            "{GROUPNAME} = nome do grupo",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancelar", callback_data="bv_cancelar")]]),
            parse_mode="Markdown"
        )

    elif dados == "bv_edmidia":
        ESTADOS_FLUXO[(chat_id, user_id)] = "aguardando_midia"
        await query.message.edit_text(
            "🎞️ **Agora envie uma foto, vídeo ou figurinha!**\n\n"
            "Pode colocar legenda junto se quiser.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancelar", callback_data="bv_cancelar")]]),
            parse_mode="Markdown"
        )

    elif dados == "bv_edbotao":
        ESTADOS_FLUXO[(chat_id, user_id)] = "aguardando_botao"
        await query.message.edit_text(
            "🔲 **Agora envie o botão no formato:**\n\n"
            "`Texto - Link`\n\n"
            "Exemplo:\n`ACESSAR GRUPO - https://t.me/seulink`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancelar", callback_data="bv_cancelar")]]),
            parse_mode="Markdown"
        )

    # ✅ === VER TEXTO — MOSTRA O TEXTO INTEIRO ===
    elif dados == "bv_vertxt":
        texto, _, _, _ = carregar_dados_bv(chat_id)
        if not texto:
            texto = f"📄 **USANDO TEXTO PADRÃO:**\n\n{TEXTO_PADRAO}"
        await query.message.edit_text(
            f"📄 **TEXTO QUE SERÁ ENVIADO:**\n\n{texto}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]]),
            parse_mode="Markdown"
        )

    # ✅ === VER MÍDIA — ENVIA A MÍDIA DE VERDADE ===
    elif dados == "bv_vermidia":
        _, midia, _, _ = carregar_dados_bv(chat_id)
        if not midia:
            await query.message.edit_text(
                "❌ **Nenhuma mídia salva.**\nSerá enviado apenas o texto.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]]),
                parse_mode="Markdown"
            )
        else:
            tipo, file_id, legenda = midia
            info = f"🎞️ **MÍDIA SALVA:** {tipo.upper()}\n\n"
            if legenda:
                info += f"📝 **Legenda:** {legenda}\n\n"
            info += "✅ Enviando a mídia abaixo EXATAMENTE como aparecerá para o novo membro:"
            await query.message.edit_text(info, parse_mode="Markdown")
            # ✅ ENVIA A MÍDIA DE VERDADE PRA VOCÊ VER
            try:
                if tipo == "photo":
                    await query.message.reply_photo(file_id, caption=legenda or "📸 Foto que será enviada")
                elif tipo == "video":
                    await query.message.reply_video(file_id, caption=legenda or "🎬 Vídeo que será enviado", supports_streaming=True)
                elif tipo == "sticker":
                    await query.message.reply_sticker(file_id)
                    await query.message.reply_text("😊 Figurinha que será enviada")
            except Exception as e:
                await query.message.reply_text(f"⚠️ Não foi possível exibir a mídia: {e}")

    # ✅ === VER BOTÃO — MOSTRA TEXTO E LINK ===
    elif dados == "bv_verbotao":
        _, _, botoes, _ = carregar_dados_bv(chat_id)
        if not botoes:
            await query.message.edit_text(
                f"🔲 **Nenhum botão salvo.**\nSerá usado o PADRÃO:\n\nTexto: 💎 ACESSAR CONTEÚDO 💎\nLink: {LINK_BOT_PADRAO}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]]),
                parse_mode="Markdown"
            )
        else:
            texto_bot = botoes.inline_keyboard[0][0].text
            link_bot = botoes.inline_keyboard[0][0].url
            await query.message.edit_text(
                f"🔲 **BOTÃO CONFIGURADO:**\n\n"
                f"📝 **Texto:** {texto_bot}\n"
                f"🔗 **Link:** {link_bot}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(texto_bot, url=link_bot)],
                    [InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]
                ]),
                parse_mode="Markdown"
            )

    elif dados == "bv_cancelar":
        ESTADOS_FLUXO.pop((chat_id, user_id), None)
        await painel_principal(update, context, chat_id, msg_ref=query.message)

async def capturar_dados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chave = (chat_id, user_id)

    if chave not in ESTADOS_FLUXO:
        return

    estado = ESTADOS_FLUXO.pop(chave)
    aviso = ""

    if estado == "aguardando_texto":
        texto = update.message.text or update.message.caption or ""
        salvar_bv(chat_id, "texto", texto)
        aviso = "✅ **TEXTO SALVO! Substituído com sucesso!**"

    elif estado == "aguardando_midia":
        legenda = update.message.caption or ""
        if update.message.photo:
            arquivo = update.message.photo[-1]
            salvar_bv(chat_id, "midia", ("photo", arquivo.file_id, legenda))
            aviso = "✅ **FOTO SALVA! Substituída a anterior!**"
        elif update.message.video:
            arquivo = update.message.video
            salvar_bv(chat_id, "midia", ("video", arquivo.file_id, legenda))
            aviso = "✅ **VÍDEO SALVO! Substituído o anterior!**"
        elif update.message.sticker:
            arquivo = update.message.sticker
            salvar_bv(chat_id, "midia", ("sticker", arquivo.file_id, legenda))
            aviso = "✅ **FIGURINHA SALVA! Substituída a anterior!**"

    elif estado == "aguardando_botao":
        texto = update.message.text or ""
        if " - " in texto:
            titulo, link = texto.split(" - ", 1)
            teclado = InlineKeyboardMarkup([[InlineKeyboardButton(titulo.strip(), url=link.strip())]])
            salvar_bv(chat_id, "botoes", teclado)
            aviso = f"✅ **BOTÃO SALVO!**\nTexto: {titulo.strip()}\nLink: {link.strip()}"
        else:
            aviso = "⚠️ Formato errado! Use: `Texto - Link`"

    if aviso:
        await update.message.reply_text(aviso, parse_mode="Markdown")
        await painel_principal(update, context, chat_id)

# ✅ === REGISTRAR TUDO ===
def registrar_bemvindo(application):
    application.add_handler(CommandHandler("bemvindo", cmd_bemvindo))
    application.add_handler(CallbackQueryHandler(botoes_painel, pattern=r"^bv_"))
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Sticker.ALL & ~filters.COMMAND & filters.ChatType.PRIVATE,
        capturar_dados
    ))
    # ✅ HANDLER CORRIGIDO — FUNCIONA NOS GRUPOS
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        novo_membro_handler
    ))
