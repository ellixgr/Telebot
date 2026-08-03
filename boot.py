import asyncio, os, time, re
from pymongo import MongoClient

# ==============================================
# ✅ CARREGA TUDO DAS VARIÁVEIS DO AMBIENTE
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
# ✅ TÓPICOS COM NOMES (IDs REAIS SERÃO DESCOBERTOS AUTOMATICAMENTE)
# ==============================================
TOPICOS_PARA_PROCESSAR = [
    "álbum faveladas",
    "álbum lives faveladinhas",
    "álbum funk faveladas",
    "álbum TikTok faveladas",
    "álbum flagra na rua",
    "álbum lives faveladas",
    "Câmeras escondidas",
    "álbum trans",
    "álbum corninhos",
    "álbum omegle",
    "só as gordinhas",
    "álbum xvideos red",
    "álbum anãs",
    "álbum amadoras",
]

# ==============================================
# ✅ CONEXÃO COM MONGODB
# ==============================================
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    db = mongo_client["sanizinhabot_db"]
    coll_enviados = db["midias_enviadas"]
    coll_topicos_concluidos = db["topicos_concluidos"]
    coll_topicos_nomes = db["topicos_nomes"]  # Salva nome → id real
    print("✅ Conectado ao MongoDB!")
except Exception as e:
    print(f"⚠️ ERRO MongoDB: {e}")
    exit(1)

# ==============================================
# ✅ GERA A HASHTAG SEM A PALAVRA "ÁLBUM"
# ==============================================
def gerar_hashtag(nome_topico):
    nome_limpo = re.sub(r"álbum\s+", "", nome_topico, flags=re.IGNORECASE).strip()
    sem_acentos = nome_limpo.lower()
    sem_acentos = sem_acentos.replace(" ", "").replace("ã", "a").replace("ç", "c").replace("í", "i").replace("á", "a").replace("ô", "o").replace("ê", "e")
    return f"#{sem_acentos}"

# ==============================================
# ✅ VERIFICA SE JÁ FOI ENVIADO
# ==============================================
def ja_foi_enviado(msg_id, nome, tam_bytes):
    return coll_enviados.find_one({
        "$or": [
            {"msg_id": str(msg_id)},
            {"chave_unica": f"{nome}|{tam_bytes}"}
        ]
    }) is not None

# ==============================================
# ✅ SALVA COMO ENVIADO
# ==============================================
def salvar_enviado(msg_id, nome, tam_bytes, id_topico):
    coll_enviados.insert_one({
        "msg_id": str(msg_id),
        "nome": nome,
        "tamanho_bytes": tam_bytes,
        "chave_unica": f"{nome}|{tam_bytes}",
        "topico_id": id_topico,
        "enviado_em": time.time()
    })

# ==============================================
# ✅ MARCA TÓPICO COMO CONCLUÍDO
# ==============================================
def topico_ja_concluido(nome_topico):
    return coll_topicos_concluidos.find_one({"nome_topico": nome_topico}) is not None

def marcar_topico_concluido(nome_topico, id_topico, total_itens):
    coll_topicos_concluidos.update_one(
        {"nome_topico": nome_topico},
        {"$set": {
            "topico_id": id_topico,
            "total_itens": total_itens,
            "concluido_em": time.time()
        }},
        upsert=True
    )

# ==============================================
# ✅ DESCOBRE O ID REAL DO TÓPICO PELO NOME NAS MENSAGENS
# ==============================================
async def descobrir_id_topico(app, nome_topico):
    # Primeiro tenta buscar do banco
    salvo = coll_topicos_nomes.find_one({"nome": nome_topico})
    if salvo:
        return salvo["topico_id"]

    nome_busca = re.sub(r"álbum\s+", "", nome_topico, flags=re.IGNORECASE).strip().lower()
    contagem_ids = {}

    async for msg in app.get_chat_history(GRUPO_ORIGEM, limit=5000):
        tid = getattr(msg, 'topic_id', None) or getattr(msg, 'reply_to_message_id', None)
        if not tid:
            continue
        if msg.video or msg.photo:
            legenda = (msg.caption or "").lower()
            if any(palavra in legenda for palavra in nome_busca.split()):
                contagem_ids[tid] = contagem_ids.get(tid, 0) + 1
        if len(contagem_ids) > 10:
            break

    if contagem_ids:
        id_real = max(contagem_ids, key=contagem_ids.get)
        coll_topicos_nomes.update_one({"nome": nome_topico}, {"$set": {"topico_id": id_real}}, upsert=True)
        print(f"🔍 ID REAL DESCOBERTO: '{nome_topico}' → {id_real}")
        return id_real

    print(f"⚠️ Não foi possível descobrir ID de: {nome_topico}")
    return None

# ==============================================
# ✅ PROCESSAR UM TÓPICO INTEIRO
# ==============================================
async def processar_topico(app, nome_topico):
    print(f"\n{'='*70}")
    print(f"🚀 INICIANDO TÓPICO — {nome_topico}")
    print(f"{'='*70}")

    if topico_ja_concluido(nome_topico):
        print(f"✅ TÓPICO JÁ CONCLUÍDO ANTES → PULANDO!\n")
        return 0

    id_topico = await descobrir_id_topico(app, nome_topico)
    if not id_topico:
        print(f"❌ Sem ID → pulando esse tópico\n")
        return 0

    hashtag = gerar_hashtag(nome_topico)
    todas_msg = []
    ultimo_id = 0
    lote_tamanho = 200

    while True:
        lote = []
        async for msg in app.get_chat_history(GRUPO_ORIGEM, limit=lote_tamanho, offset_id=ultimo_id):
            ultimo_id = msg.id
            msg_topico = getattr(msg, 'topic_id', None) or getattr(msg, 'reply_to_message_id', None)
            if msg_topico != id_topico:
                continue
            if not msg.video and not msg.photo:
                continue
            lote.append(msg)

        if not lote:
            break
        todas_msg.extend(lote)
        if len(lote) < lote_tamanho:
            break
        await asyncio.sleep(0.3)

    if not todas_msg:
        print(f"✅ TÓPICO: Nenhum item NOVO!\n")
        marcar_topico_concluido(nome_topico, id_topico, 0)
        return 0

    todas_msg.reverse()
    print(f"✅ {len(todas_msg)} itens encontrados! Preparando envio...\n")

    # ✅ AGRUPA MENSAGENS
    grupos = []
    grupo_atual = []

    for msg in todas_msg:
        msg_id = msg.id
        eh_video = bool(msg.video)
        eh_foto = bool(msg.photo)
        if not eh_video and not eh_foto:
            continue

        tem_grupo = getattr(msg, 'media_group_id', None)
        legenda_original = msg.caption or ""

        if eh_video:
            midia = msg.video
            nome = midia.file_name or f"video_{msg_id}.mp4"
            tam_bytes = midia.file_size or 0
        else:
            midia = msg.photo
            nome = f"foto_{msg_id}.jpg"
            tam_bytes = 0

        legenda_final = legenda_original.strip() if legenda_original else hashtag

        item = {
            "msg_id": msg_id,
            "nome": nome,
            "tam_bytes": tam_bytes,
            "midia": midia,
            "tipo": "VÍDEO" if eh_video else "FOTO",
            "legenda": legenda_final,
            "grupo_id": tem_grupo
        }

        if ja_foi_enviado(msg_id, nome, tam_bytes):
            if grupo_atual:
                grupos.append(grupo_atual)
                grupo_atual = []
            continue

        if tem_grupo:
            if not grupo_atual or grupo_atual[0]["grupo_id"] == tem_grupo:
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
        marcar_topico_concluido(nome_topico, id_topico, 0)
        return 0

    # ✅ ENVIAR OS GRUPOS
    from pyrogram.types import InputMediaPhoto, InputMediaVideo
    total_enviados = 0
    contador = 0

    for grupo in grupos:
        contador += 1
        qtd = len(grupo)
        legenda_grupo = grupo[0]["legenda"]

        tam_mb = round(grupo[0]["tam_bytes"] / 1048576, 2) if grupo[0]["tam_bytes"] > 0 else "foto"
        if qtd > 1:
            print(f"📦 [{contador}/{len(grupos)}] AGRUPAMENTO DE {qtd} MÍDIAS")
        else:
            print(f"📤 [{contador}/{len(grupos)}] {grupo[0]['tipo']} {tam_mb} → {grupo[0]['nome'][:35]} | {legenda_grupo}")

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

            # ✅ SALVA NO BANCO
            for item in grupo:
                salvar_enviado(item["msg_id"], item["nome"], item["tam_bytes"], id_topico)

            total_enviados += len(caminhos)

            # ✅ APAGA ARQUIVO
            for m in caminhos:
                try: os.remove(m["caminho"])
                except: pass

            # ✅ PAUSA
            if qtd > 3 or (tam_mb != "foto" and float(tam_mb) > 50):
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(1)

        except Exception as e:
            erro = str(e)[:80]
            print(f"❌ ERRO: {erro}\n")
            await asyncio.sleep(2)

    marcar_topico_concluido(nome_topico, id_topico, total_enviados)
    print(f"\n🏁 TÓPICO CONCLUÍDO! Enviados: {total_enviados} itens\n")
    return total_enviados

# ==============================================
# ✅ FUNÇÃO PRINCIPAL
# ==============================================
async def main():
    from pyrogram import Client
    async with Client("minha_conta", API_ID, API_HASH, phone_number=TELEFONE) as app:
        print(f"🔌 CONECTADO! Iniciando processamento dos tópicos...\n")

        total_geral = 0
        for nome_topico in TOPICOS_PARA_PROCESSAR:
            qtd = await processar_topico(app, nome_topico)
            total_geral += qtd
            print(f"⏳ Pausa 3s antes do próximo tópico...\n")
            await asyncio.sleep(3)

        print(f"\n{'='*70}")
        print(f"🏆 TODOS OS TÓPICOS CONCLUÍDOS!")
        print(f"📋 TOTAL ENVIADO: {total_geral} itens")
        print(f"📊 Total salvo no MongoDB: {coll_enviados.estimated_document_count()} itens")
        print(f"{'='*70}")

if __name__ == "__main__":
    asyncio.run(main())
