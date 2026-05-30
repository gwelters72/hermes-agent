import threading
import asyncio
import logging
import functools
import openai

logger = logging.getLogger(__name__)

# Globale Locks für die GPU-Ressource
_GPU_SYNC_LOCK = threading.Lock()
_GPU_ASYNC_LOCK = asyncio.Lock()

def wrap_create(original_create, client_instance, is_async=False):
    if is_async:
        @functools.wraps(original_create)
        async def locked_create(*args, **kwargs):
            from agent.model_metadata import is_local_endpoint
            base_url = str(client_instance.base_url)
            if is_local_endpoint(base_url):
                # logger.debug(f"[GPU-Sync] Serializing async request to {base_url}")
                async with _GPU_ASYNC_LOCK:
                    return await original_create(*args, **kwargs)
            return await original_create(*args, **kwargs)
        return locked_create
    else:
        @functools.wraps(original_create)
        def locked_create(*args, **kwargs):
            from agent.model_metadata import is_local_endpoint
            base_url = str(client_instance.base_url)
            if is_local_endpoint(base_url):
                # logger.debug(f"[GPU-Sync] Serializing sync request to {base_url}")
                with _GPU_SYNC_LOCK:
                    return original_create(*args, **kwargs)
            return original_create(*args, **kwargs)
        return locked_create

def patch_openai_classes():
    # Sync OpenAI patch
    orig_init = openai.OpenAI.__init__
    @functools.wraps(orig_init)
    def new_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self.chat.completions.create = wrap_create(
            self.chat.completions.create, self, is_async=False
        )
    openai.OpenAI.__init__ = new_init

    # Async OpenAI patch
    orig_async_init = openai.AsyncOpenAI.__init__
    @functools.wraps(orig_async_init)
    def new_async_init(self, *args, **kwargs):
        orig_async_init(self, *args, **kwargs)
        self.chat.completions.create = wrap_create(
            self.chat.completions.create, self, is_async=True
        )
    openai.AsyncOpenAI.__init__ = new_async_init
    
    logger.info("GPU Sync Enforcer: OpenAI/AsyncOpenAI patched for local sequential access.")

def register(ctx):
    """Hermes plugin entry point."""
    patch_openai_classes()
