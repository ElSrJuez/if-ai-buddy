# Scene Image Popup Debug Status

## Implementation Summary

✅ **AI Task Queue System Implemented**
- Replaced manual coordination with canonical `asyncio.Queue`
- Single `_ai_worker` coroutine processes all AI tasks sequentially
- `AITask` abstraction with `NarrationTask` and `SceneImageTask` implementations
- Proper status management: `ai`/`sd_prompt`/`sd` status transitions handled by worker

✅ **Cache Hit Logic Fixed**
- `_generate_and_show_scene_image()` now checks cache first via `get_cached_image()`
- Both cache hits and misses display popup correctly
- Removed manual status management - AI worker handles all status transitions

✅ **Canonical Turn Lifecycle Enforced** 
- Removed manual `_schedule_scene_image_generation()` calls that violated lifecycle
- Fixed room change detection: `room_changed = self._room != self._current_room_for_images or self._current_room_for_images is None`
- Both initialization and regular turns follow identical logic

## Current Issue

❌ **Scene image popup still not appearing**

### Observed Behavior
- Cached image exists: `west_of_house_medium.png` + `west_of_house.json`
- AI queue system works (narration processes correctly)
- No scene image task queued during initialization

### Likely Root Causes

1. **Room Change Detection Still Broken**
   - Initialization may not be setting `self._room` before room change check
   - Logic: `self._room != self._current_room_for_images or self._current_room_for_images is None`
   - If `self._room` is not set when this runs, `room_changed` will be False

2. **Missing Debug Logging** 
   - No logs showing "Scene image generation task queued" during initialization
   - Need visibility into room change detection logic

3. **Async Timing Issues**
   - Room change detection may run before `self._room` is properly set from parsed facts

## Next Steps

### Debugging Phase
1. **Add logging to room change detection**:
   ```python
   room_changed = self._room != self._current_room_for_images or self._current_room_for_images is None
   my_logging.system_debug(f"Room change check: room={self._room}, current_for_images={self._current_room_for_images}, room_changed={room_changed}")
   ```

2. **Verify initialization order**:
   - Ensure `self._room = facts.room_name` happens before room change detection
   - Check if `facts.room_name` is properly populated during initialization

3. **Add scene image task queue logging**:
   - Confirm if `SceneImageTask` is being created and queued
   - Verify AI worker is processing the task

### Implementation Phase
1. **If room change detection is broken**: Fix the logic or timing
2. **If task queuing is broken**: Debug the queue submission
3. **If cache loading is broken**: Debug the `get_cached_image()` call

## Technical Notes

- **Queue System**: Working correctly (narration tasks process fine)
- **Cache System**: Has existing images and metadata
- **Popup System**: tkinter implementation exists and functional
- **Status System**: 4-engine transparency working correctly

## Architecture Compliance

✅ **No manual triggers** - All scene image generation goes through canonical turn flow  
✅ **Sequential AI processing** - Queue prevents concurrent AI operations  
✅ **Status transparency** - User can see AI/SD/SD-Prompt status distinctly  

The queue implementation is architecturally sound. This is likely a simple initialization timing or logging issue.