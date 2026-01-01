# AI Task Queuing System

## Problem Statement

Current implementation violates the **single AI task execution** principle by allowing concurrent execution of:
- Narration LLM tasks (AI status)
- Scene Image Prompt generation LLM tasks (SD Prompt status) 
- Scene Image generation (SD status)

**Evidence**: Status bar showing both `AI: Working` and `SD: Generating` simultaneously.

## Current Implementation Analysis

### What We Have (Broken)
- **Not a queue**: Each `_schedule_narration_job()` immediately creates `asyncio.create_task()`
- **Concurrent execution**: Multiple narration tasks can run simultaneously via `_narration_tasks` set
- **Manual coordination**: Checking `_active_narration_jobs > 0` to prevent scene image generation
- **Race conditions**: Scene image scheduling happens before narration scheduling

### Root Cause
The sequence in `_execute_turn()`:
1. Scene image generation triggered (when `_active_narration_jobs` is still 0)
2. Narration job scheduled (increments `_active_narration_jobs`)
3. Both run concurrently

## Canonical Solution: asyncio.Queue

Based on Context7 research, the canonical Python approach is **`asyncio.Queue`** with a **single worker coroutine**.

### Producer-Consumer Pattern
```python
# Single AI worker processes all tasks sequentially
async def ai_worker(queue):
    while True:
        ai_task = await queue.get()
        try:
            await ai_task.execute()
        finally:
            queue.task_done()

# Tasks are queued, not executed immediately
await queue.put(narration_task)
await queue.put(scene_image_task)
```

### Benefits
- **Atomic**: Only one AI task executes at a time
- **Canonical**: Standard Python asyncio pattern
- **Elegant**: No manual coordination needed
- **FIFO ordering**: Tasks execute in submission order
- **Exception safe**: `finally` ensures `task_done()` is called

## Implementation Plan

### 1. Create AI Task Abstraction
```python
from abc import ABC, abstractmethod

class AITask(ABC):
    """Abstract base class for all AI tasks."""
    
    @abstractmethod
    async def execute(self) -> None:
        """Execute the AI task."""
        pass
    
    @abstractmethod
    def get_status_type(self) -> str:
        """Return status type: 'ai', 'sd_prompt', 'sd'"""
        pass

class NarrationTask(AITask):
    def __init__(self, job_spec: NarrationJobSpec, room: str):
        self.job_spec = job_spec
        self.room = room
    
    async def execute(self) -> None:
        # Current _run_narration_job logic
        pass
    
    def get_status_type(self) -> str:
        return "ai"

class SceneImageTask(AITask):
    def __init__(self, room_name: str, memory_context: dict):
        self.room_name = room_name
        self.memory_context = memory_context
    
    async def execute(self) -> None:
        # Current _generate_and_show_scene_image logic
        pass
    
    def get_status_type(self) -> str:
        return "sd"
```

### 2. Single AI Worker
```python
class GameController:
    def __init__(self):
        self._ai_queue = asyncio.Queue()
        self._ai_worker_task = None
        
    async def start(self):
        """Start the AI worker."""
        self._ai_worker_task = asyncio.create_task(self._ai_worker())
    
    async def _ai_worker(self):
        """Single worker processes all AI tasks sequentially."""
        while True:
            try:
                task = await self._ai_queue.get()
                
                # Set appropriate status
                if task.get_status_type() == "ai":
                    self._set_ai_status(AIStatus.WORKING)
                elif task.get_status_type() == "sd_prompt":
                    self._set_sd_prompt_status(SDPromptStatus.WORKING)
                elif task.get_status_type() == "sd":
                    self._set_sd_status(SDStatus.GENERATING)
                
                # Execute task
                await task.execute()
                
                # Reset status
                if task.get_status_type() == "ai":
                    self._set_ai_status(AIStatus.READY)
                elif task.get_status_type() == "sd_prompt":
                    self._set_sd_prompt_status(SDPromptStatus.READY)
                elif task.get_status_type() == "sd":
                    self._set_sd_status(SDStatus.READY)
                    
            except Exception as exc:
                my_logging.system_warn(f"AI task failed: {exc}")
                # Set error status based on task type
            finally:
                self._ai_queue.task_done()
```

### 3. Replace Manual Scheduling
```python
# Old (broken):
def _schedule_narration_job(self, job_spec, room):
    task = asyncio.create_task(self._run_narration_job(job_spec, room))
    # Multiple tasks can run concurrently

# New (proper queue):
def _schedule_narration_job(self, job_spec, room):
    task = NarrationTask(job_spec, room)
    asyncio.create_task(self._ai_queue.put(task))

def _schedule_scene_image_generation(self):
    memory_context = self._memory.get_context_for_prompt()
    task = SceneImageTask(self._room, memory_context)
    asyncio.create_task(self._ai_queue.put(task))
```

### 4. Cleanup Manual Coordination
Remove all manual coordination code:
- `_active_narration_jobs` counter
- `_schedule_deferred_scene_image` flag
- Deferred execution logic in `_on_narration_done`
- Manual status checking

## Migration Strategy

1. **Create AI task abstractions** (new files)
2. **Add queue and worker to GameController**
3. **Replace scheduling calls** (minimal changes)
4. **Remove manual coordination** (cleanup)
5. **Test single AI task execution**

## Expected Outcome

Status bar will show proper sequential execution:
- `AI: Working` (narration)
- `AI: Ready`, `SD Prompt: Working` (generating diffusion prompt)  
- `SD Prompt: Ready`, `SD: Generating` (creating image)
- `SD: Ready` (complete)

Never concurrent AI operations.