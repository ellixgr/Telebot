import asyncio, os, time, re
from pymongo import MongoClient

# ==============================================
# ✅ CONFIGURAÇÕES
# ==============================================
API_ID = int(os.environ.get("API_ID", 33403443))
API_HASH = os.environ.get("API_HASH", "a8e904f52fdd49469903f90120fc8e04")
TELEFONE = os.environ.get("TELEFONE", "+5521977231625")
GRUPO_ORIGEM = int(os.environ.get("GRUPO_ORIGEM", -1003090522608))
GRUPO_DESTINO = int(os.environ.get("GRUPO_DESTINO", -1004399892914))
MONGO_URI = os.environ.get("MONGO_URI", "")

PASTA_TEMP = "/tmp/bot_temp/"
os.makedirs(PASTA_TEMP, exist_ok=True)

# ==============================================
# ✅ TODOS OS TÓPICOS COM IDs REAIS (DOS SEUS LINKS!)
# ==============================================
TOPICOS = [
    (3755, "faveladas"),
    (3754, "live faveladinhas"),
    (15606, "funk faveladinhas"),
    (11245, "TikTok faveladas"),
    (11604, "flagra na rua"),
    (11954, "live faveladas"),
    (12744, "Câmeras escondidas"),
    (13016, "álbum trans"),
    (15281, "álbum corninhos"),
    (20409, "álbum omegle"),
    (22342, "só as gordinhas"),
    (21210, "álbum xvideos red"),
    (21965, "álbum anãs"),
    (23320, "álbum amadoras"),
]

# ==============================================
# ✅ CONEXÃO MONGODB
# ==============================================
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    db = mongo_client["sanizinhabot_db"]
    coll_enviados = db["midias_enviadas"]
    coll_topicos_concluidos = db["topicos_concluidos"]
    print("✅ Conectado ao MongoDB!")
except Exception as e:
    print(f"⚠️ ERRO MongoDB: {e}")
    exit(1)

# ==============================================
# ✅ HASHTAG
# ==============================================
def gerar_hashtag(nome):
    limpo = re.sub(r"álbum\s+", "", nome, flags=re.IGNORECASE).strip().lower()
    limpo = re.sub(r"[^\w]", "", limpo)
    return f"#{limpo}"

# ==============================================
# ✅ CONTROLE DE ENVIADOS
# ==============================================
def ja_enviado(msg_id, nome, tam):
    return coll_enviados.find_one({"$or": [{"msg_id": str(msg_id)}, {"chave": f"{nome}|{tam}"}]}) is not None

def salvar_enviado(msg_id, nome, tam, topico_id):
    coll_enviados.insert_one({
        "msg_id": str(msg_id), "nome": nome, "tam_bytes": tam,
        "chave": f"{nome}|{tam}", "topico_id": topico_id, "enviado_em": time.time()
    })

def topico_concluido(tid):
    return coll_topicos_concluidos.find_one({"topico_id": tid}) is not None

def marcar_concluido(tid, nome, total):
    coll_topicos_concluidos.update_one({"topico_id": tid}, {"$set": {"nome": nome, "total": total, "concluido_em": time.time()}}, upsert=True)

# ==============================================
# ✅ PROCESSAR 1 TÓPICO
# ==============================================
async def processar(app, topico_id, nome_topico):
    print(f"\n{'='*70}")
    print(f"🚀 TÓPICO {topico_id} — {nome_topico}")
    print(f"{'='*70}")

    if topico_concluido(topico_id):
        print(f"✅ JÁ CONCLUÍDO → PULANDO!\n")
        return 0

    hashtag = gerar_hashtag(nome_topico)
    mensagens = []
    ultimo_id = 0
    lote_tam = 200

    while True:
        lote = []
        async for msg in app.get_chat_history(GRUPO_ORIGEM, limit=lote_tam, offset_id=ultimo_id):
            ultimo_id = msg.id
            tid = getattr(msg, 'topic_id', None) or getattr(msg, 'reply_to_message_id', None)
            if tid != topico_id:
                continue
            if not msg.video and not msg.photo:
                continue
            lote.append(msg)
        if not lote:
            break
        mensagens.extend(lote)
        if len(lote) < lote_tam:
            break
        await asyncio.sleep(0.3)

    if not mensagens:
        print(f"✅ Nenhum item encontrado!\n")
        marcar_concluido(topico_id, nome_topico, 0)
        return 0

    mensagens.reverse()
    print(f"✅ {len(mensagens)} itens encontrados! Preparando envio...\n")

    # AGRUPAR E ENVIAR
    from pyrogram.types import InputMediaPhoto, InputMediaVideo
    grupos = []
    grupo_atual = []

    for msg in mensagens:
        msg_id = msg.id
        eh_video = bool(msg.video)
        eh_foto = bool(msg.photo)
        if not eh_video and not eh_foto:
            continue

        midia_grupo = getattr(msg, 'media_group_id', None)
        legenda = (msg.caption or "").strip() or hashtag

        if eh_video:
            midia = msg.video
            nome_arq = midia.file_name or f"video_{msg_id}.mp4"
            tam_bytes = midia.file_size or 0
        else:
            midia = msg.photo
            nome_arq = f"foto_{msg_id}.jpg"
            tam_bytes = 0

        if ja_enviado(msg_id, nome_arq, tam_bytes):
            if grupo_atual:
                grupos.append(grupo_atual)
                grupo_atual = []
            continue

        item = {
            "id": msg_id, "nome": nome_arq, "tam": tam_bytes,
            "midia": midia, "tipo": "VÍDEO" if eh_video else "FOTO",
            "legenda": legenda, "grupo_id": midia_grupo
        }

        if midia_grupo:
            if not grupo_atual or grupo_atual[0]["grupo_id"] == midia_grupo:
                grupo_atual.append(item)
            else:
                grupos.append(grupo_atual)
                grupo_atual = [item]
        else:
            if grupo_atual:
                grupos.append(grupo_atual)
                grupo_atual = []
            grupos.append([item])

    if grupo_atual:
        grupos.append(grupo_atual)

    if not grupos:
        print(f"✅ Nenhum item NOVO!\n")
        marcar_concluido(topico_id, nome_topico, 0)
        return 0

    total_enviados = 0
    contador = 0

    for grupo in grupos:
        contador += 1
        qtd = len(grupo)
        legenda_grupo = grupo[0]["legenda"]
        tam_mb = round(grupo[0]["tam"]/1048576,2) if grupo[0]["tam"]>0 else "foto"

        if qtd > 1:
            print(f"📦 [{contador}/{len(grupos)}] AGRUPAMENTO DE {qtd} MÍDIAS")
        else:
            print(f"📤 [{contador}/{len(grupos)}] {grupo[0]['tipo']} {tam_mb} → {grupo[0]['nome'][:35]}")

        try:
            caminhos = []
            for item in grupo:
                cam = await app.download_media(item["midia"], PASTA_TEMP + item["nome"])
                if not cam or os.path.getsize(cam) == 0:
                    continue
                caminhos.append({**item, "caminho": cam})

            if not caminhos:
                print(f"⚠️ Arquivo vazio → pulando\n")
                continue

            if len(caminhos) > 1:
                lote_midia = []
                for i, m in enumerate(caminhos):
                    leg = legenda_grupo if i == 0 else ""
                    if m["tipo"] == "FOTO":
                        lote_midia.append(InputMediaPhoto(m["caminho"], caption=leg))
                    else:
                        lote_midia.append(InputMediaVideo(m["caminho"], caption=leg, supports_streaming=True))
                await app.send_media_group(GRUPO_DESTINO, media=lote_midia)
                print(f"✅ ENVIADO AGRUPADO!\n")
            else:
                m = caminhos[0]
                if m["tipo"] == "VÍDEO":
                    await app.send_video(GRUPO_DESTINO, m["caminho"], caption=m["legenda"], supports_streaming=True)
                else:
                    await app.send_photo(GRUPO_DESTINO, m["caminho"], caption=m["legenda"])
                print(f"✅ ENVIADO!\n")

            for item in grupo:
                salvar_enviado(item["id"], item["nome"], item["tam"], topico_id)
            total_enviados += len(caminhos)

            for m in caminhos:
                try: os.remove(m["caminho"])
                except: pass

            await asyncio.sleep(1.5 if qtd<=3 and (tam_mb=="foto" or float(tam_mb)<=50) else 2.5)

        except Exception as e:
            print(f"❌ ERRO: {str(e)[:80]}\n")
            await asyncio.sleep(2)

    marcar_concluido(topico_id, nome_topico, total_enviados)
    print(f"\n🏁 TÓPICO CONCLUÍDO! Enviados: {total_enviados} itens\n")
    return total_enviados

# ==============================================
# ✅ MAIN
# ==============================================
async def main():
    from pyrogram import Client
    async with Client("minha_conta", API_ID, API_HASH, phone_number=TELEFONE) as app:
        print(f"🔌 CONECTADO! Iniciando...\n")
        total_geral = 0
        for tid, nome in TOPICOS:
            qtd = await processar(app, tid, nome)
            total_geral += qtd
            print(f"⏳ Pausa 3s antes do próximo...\n")
            await asyncio.sleep(3)
        print(f"\n{'='*70}")
        print(f"🏆 TOTAL ENVIADO: {total_geral} itens")
        print(f"📊 Salvo no banco: {coll_enviados.estimated_document_count()} itens")
        print(f"{'='*70}")

if __name__ == "__main__":
    asyncio.run(main())
