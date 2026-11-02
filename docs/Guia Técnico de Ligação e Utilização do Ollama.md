# Manual Técnico: Ligação, Otimização e Gestão de Memória no Ollama

Este documento explica o funcionamento interno do **Ollama**, os desafios de
modelos de visão multimodal (VLM) em GPUs de entrada (como a NVIDIA GTX 1050 Ti
de 4 GB), a variante `qwen2.5vl:light` e as regras de orquestração do serviço.

---

## 1. O Problema Fundamental: Arquitetura de Visão e VRAM

### 1.1 O que provoca o erro

Ao correr:

```bash
ollama run qwen2.5vl:3b "..." ./foto.jpg
```

Surge, em máquinas com pouca VRAM:

```text
ggml_gallocr_reserve_n_impl: failed to allocate Vulkan0 buffer of size 1226281472
ggml_backend_sched_alloc_splits: failed to reserve graph buffers
clip_encode: failed to allocate compute graph
```

### 1.2 Porquê

1. **Dois módulos no mesmo modelo**
   - **Codificador visual (Vision Tower / CLIP):** divide a imagem numa grelha
     de patches (tipicamente 14×14 px) e calcula tensores visuais.
   - **Modelo de linguagem (LLM):** recebe esses vetores como se fossem tokens e
     gera a resposta em texto.

2. **Buffer de grafo multimodal:** para processar fotos grandes, o `clip_encode`
   cria um grafo temporário na GPU. O erro indica uma tentativa de alocar um
   bloco contínuo de **~1,14 GB** (`1226281472` bytes) só para esse grafo.

3. **Limite da GTX 1050 Ti (4 GB):**
   - ambiente gráfico (Xorg/Wayland, browser) consome 500 MB–1 GB;
   - pesos do 3B quantizado (Q4) ocupam ~2,2 GB;
   - sobram menos de 1 GB — e o buffer visual precisa de 1,14 GB contíguos.

---

## 2. A Solução: Variante `qwen2.5vl:light`

Reduz-se a janela de contexto e o teto de geração com um **`Modelfile`** — o
equivalente a um `Dockerfile` para modelos Ollama. O ficheiro está na raiz do
projeto: [`Modelfile`](../Modelfile).

### 2.1 Conteúdo

```dockerfile
FROM qwen2.5vl:3b

# Janela de contexto global (prompt + histórico + tokens visuais)
PARAMETER num_ctx 2048

# Teto de geração de tokens na resposta
PARAMETER num_predict 300

# Temperatura baixa para respostas factuais
PARAMETER temperature 0.2
```

### 2.2 O que faz cada parâmetro

| Parâmetro | Efeito |
| --- | --- |
| `FROM qwen2.5vl:3b` | reaproveita os pesos já descarregados (sem novo download) |
| `num_ctx 2048` | reduz o K-V Cache reservado; baixar de 8192 para 2048 liberta centenas de MB |
| `num_predict 300` | suficiente para título (30) + descrição (200) + categorias, sem cortar o JSON |
| `temperature 0.2` | respostas objetivas e JSON estável |

### 2.3 Compilação

```bash
ollama pull qwen2.5vl:3b
ollama create qwen2.5vl:light -f Modelfile
```

O Ollama lê o modelo base, reaproveita as camadas em disco (`transferring model
data`) e cria o manifesto local `qwen2.5vl:light`.

> **Importante:** o modelo **padrão** do projeto é `qwen2.5vl:3b`. A variante
> `light` é opcional e só é necessária em máquinas com pouca VRAM. Para a usar:
>
> ```bash
> fotoscan *.jpg -o catalogo.json -m qwen2.5vl:light
> ```
>
> ou altere `"modelo"` em `~/.config/fotoscan/config.json`.

---

## 3. Gestão de Recursos: Modo CPU Seguro

Quando a GPU não tem memória suficiente para o backend Vulkan, pode forçar-se o
Ollama a usar apenas CPU/RAM:

```bash
OLLAMA_NUM_PARALLEL=1 CUDA_VISIBLE_DEVICES="" OLLAMA_GPU_OVERHEAD=0 ollama serve
```

| Variável | Efeito |
| --- | --- |
| `CUDA_VISIBLE_DEVICES=""` | oculta a GPU; CUDA/Vulkan desativados, computação na CPU |
| `OLLAMA_NUM_PARALLEL=1` | um pedido de cada vez, sem multiplicar o K-V Cache |
| `OLLAMA_GPU_OVERHEAD=0` | sem reserva preventiva de margem de VRAM |

Estas variáveis estão em `config/config.json` → `servidor.env` e são aplicadas
pelo próprio `fotoscan` quando arranca o servidor.

---

## 4. Orquestração e Comunicação via API

O utilitário não corre `ollama run`: fala diretamente com a **API HTTP** do
Ollama (porta `11434`), através de `src/api/client.py` (`OllamaClient`).

```text
+------------------+      HTTP POST /api/generate      +-------------------+
|  fotoscan (CLI) | -------------------------------> | Servidor Ollama   |
|                  |                                  | (127.0.0.1:11434) |
|  - Redimensiona  | <------------------------------- |                   |
|  - Envia Base64  |        JSON com metadados        | - qwen2.5vl:3b    |
+------------------+                                  +-------------------+
         |
         | No fim do lote
         +--> POST /api/generate  { "keep_alive": 0 }  (liberta RAM/VRAM)
```

### 4.1 Ciclo de vida

1. **Healthcheck** — `GET http://127.0.0.1:11434/`.
   - `200 OK` → servidor já ativo (ex.: serviço `systemd`);
   - sem resposta → o script arranca `ollama serve` em segundo plano com as
     variáveis de `servidor.env` e espera até `servidor.timeout` segundos.
2. **Verificação do modelo** — `GET /api/tags`; se o modelo não estiver
   instalado, o programa termina com instruções de `ollama pull` / `ollama create`.
3. **Inferência** com gramática restrita:

   ```json
   {
     "model": "qwen2.5vl:3b",
     "prompt": "...",
     "images": ["<base64_da_imagem>"],
     "stream": false,
     "format": "json",
     "options": { "num_ctx": 2048, "num_predict": 300, "temperature": 0.2 }
   }
   ```

   - `"stream": false` — resposta só quando o JSON estiver completo;
   - `"format": "json"` — ativa a gramática do llama.cpp, impedindo texto
     conversacional à volta do objeto.

4. **Descarga de memória** — no fim (e no `atexit`), envia:

   ```json
   { "model": "qwen2.5vl:3b", "keep_alive": 0 }
   ```

   O Ollama descarrega o modelo de imediato, sem parar o serviço.

---

## 5. Resumo das Regras de Ouro

| Elemento | Regra | Motivo |
| --- | --- | --- |
| Resolução da imagem | `max_size` = **512 px** (padrão atual) | mantém o `clip_encode` sob controlo |
| Janela de contexto | `num_ctx` = 2048 | reduz o K-V Cache estático |
| Teto de saída | `num_predict` = 300 | JSON completo sem truncagem |
| Concorrência | `num_parallel` = 1 | evita duplicar contextos na RAM |
| Encerramento | `keep_alive: 0` | devolve a memória ao sistema |

> `max_size` é configurável em `~/.config/fotoscan/config.json`. Valores
> maiores (ex.: 768 px) dão mais detalhe mas aumentam o buffer visual — em 4 GB
> de VRAM, 512 px é o compromisso seguro.
