from modules.utils.commons import send_long_message, fetch_reply_chain, HistoryChatMessage
from llama_index.core import StorageContext, Settings, VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.llms import MessageRole as Role
from llama_index.core.memory import ChatMemoryBuffer
from qdrant_client import QdrantClient
from dotenv import load_dotenv
import asyncio
import google.generativeai as genai  # Google AI Studio SDK
import re
import os

load_dotenv()

client = QdrantClient(os.getenv('QDRANT_URL'), api_key=os.getenv('QDRANT_API'))
vector_store = QdrantVectorStore(client=client, enable_hybrid=True, batch_size=20, collection_name="openpilot-data-sparse")

# Use Gemini-Pro model (or 'gemini-pro-vision' for multimodal)
model = genai.GenerativeModel('gemini-pro')

Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
storage_context = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex.from_vector_store(vector_store)

async def process_message_with_llm(message, client):
    content = message.content.replace(client.user.mention, '').strip()
    if content:
        try:
            async with message.channel.typing():
                memory = ChatMemoryBuffer.from_defaults(token_limit=8192)
                context = await fetch_reply_chain(message)
                memory.set(context + [HistoryChatMessage(f"{content}", Role.USER)])
                chat_engine = index.as_chat_engine(
                    chat_mode="condense_plus_context",
                    similarity_top_k=4,
                    sparse_top_k=12,
                    vector_store_query_mode="hybrid",
                    memory=memory,
                    system_prompt=(
                        f"You are {client.user.name}, a Discord chat bot. "
                        "The topic is OpenPilot and its various forks.\n"
                        "Always provide the links to the sources of the information, if applicable. "
                        "Always give an answer to the best of your abilities."
                    ),
                    verbose=False,
                )

                # Generate response using Gemini-Pro
                chat_response = await asyncio.to_thread(model.generate_content, content)

                if not chat_response or not chat_response.text:
                    await message.channel.send("There was an error processing the message." if not chat_response else "I didn't get a response.")
                    return
                response_text = chat_response.text
                response_text = re.sub(r'^[^:]+:\s(?=[A-Z])', '', response_text)
                await send_long_message(message, response_text)
        except Exception as e:
            await message.channel.send(f"An error occurred: {str(e)}")
