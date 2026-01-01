# Scene Image Generation Feature Specification

## 🟢 IMPLEMENTATION STATUS

**Last Updated**: January 1, 2026  
**Status**: Phase 2 Complete - Core functionality working end-to-end  
**Next Developer**: Ready for Phase 3 (UI Integration) and Phase 4 (Service Integration)

### ✅ COMPLETED PHASES

**Phase 1: Core Infrastructure (COMPLETE)**
- ✅ SD-Server client with async HTTP and XML parameter embedding (`module/sd_server_client.py`)
- ✅ Scene image cache system with multi-quality tracking (`module/scene_image_cache.py`) 
- ✅ Configuration framework with environment variables (`config/scene_image_config.json`)
- ✅ All components tested and working

**Phase 2: LLM Prompt Generation (COMPLETE)**
- ✅ SceneImagePromptBuilder with template-driven meta-prompt generation (`module/scene_image_prompt_builder.py`)
- ✅ Full LLM integration using existing project infrastructure
- ✅ End-to-end flow: Game context → Meta-prompt → LLM → SD diffusion prompt
- ✅ Working test script demonstrates complete pipeline (`testing/test_scene_prompt_builder.py`)

**Phase 2: UI Components (COMPLETE - NEEDS INTEGRATION)**
- ✅ Scene image popup widget using Textual modal (`module/scene_image_popup.py`)
- ✅ Three action buttons: thumbs-down, regenerate, hide
- ✅ Non-modal interaction design
- ❌ NOT YET: Integration with main UI application

### 🟡 PENDING PHASES

**Phase 3: Service Integration (IN PROGRESS)**
- ✅ SceneImageService class created (`module/scene_image_service.py`) 
- ❌ TODO: Update service to use new prompt builder with LLM calls
- ❌ TODO: Complete cache-first workflow with proper error handling
- ❌ TODO: Scene change detection and auto-trigger logic

**Phase 4: Main Application Integration (NOT STARTED)**
- ❌ TODO: Modify `module/ui_helper.py` to support popup overlay
- ❌ TODO: Add scene image window state management  
- ❌ TODO: Connect popup to main game controller
- ❌ TODO: Keyboard shortcuts and commands

**Phase 5: LLM Queue Integration (NOT STARTED)**
- ❌ TODO: Modify `module/common_llm_layer.py` to include scene image jobs
- ❌ TODO: Priority scheduling after narration/memory tasks
- ❌ TODO: Maintain single AI task execution principle

**Phase 6: Observability & Polish (NOT STARTED)**
- ❌ TODO: Structured logging following project patterns
- ❌ TODO: Cache hit/miss statistics and performance metrics
- ❌ TODO: Integration testing and error handling refinement

---

## Overview

A pop-up AI-generated scene visualization feature that creates and displays visual representations of the current game scene. Scene images are generated asynchronously using LLM-crafted prompts sent to a remote image generation service, with caching, regeneration capabilities, and non-blocking integration with the main game loop.

## Scene Definition

In the context of IF AI Buddy, a **Scene** represents the current game location/room and its associated state:

- **Current room/location**: The player's present position in the game world
- **Scene description**: Accumulated description lines from engine output for this location
- **Visible items**: Objects currently present and observable in the scene
- **Scene context**: NPCs, environmental details, and atmospheric elements
- **Visit history**: How many times the player has been to this location

This aligns with the project's `Scene` object in `module/game_memory.py` which tracks `room_name`, `description_lines`, `current_items`, and related scene state.

## Feature Requirements

### Core Functionality

1. **Scene Image Generation**
   - Automatically trigger after all other LLM tasks have completed
   - Generate scene images based on current scene state from `GameMemoryStore`
   - Use sd-server (remote REST API) for actual image generation
   - Run completely asynchronously and non-blocking to the main game

2. **Image Caching**
   - Scene images are cached and available to all players
   - Cache key based on scene identifier, new generations (when triggered) always replace previous 
   - Cached images persist across sessions
   - Cache stored in `res/scene-img/` directory

3. **Pop-up Display Window**
   - Compact modal/overlay window displaying the generated image
   - Show the LLM prompt that was used to generate the image
   - Two action buttons:
     - **Thumbs-down button**: Regenerate the LLM prompt (keeping same scene context)
     - **Regen image button**: Regenerate the image using the existing prompt
     - **Hide image button**
   - Non-modal interaction - player can continue playing while window is open

### Technical Architecture

#### LLM Prompt Generation Flow

1. **Queue Integration**
   - Scene image generation jobs are queued in the existing LLM task queue
   - Only runs after all narration and memory tasks are complete
   - Maintains the project's principle of no simultaneous AI tasks

2. **Prompt Construction**
   - New `SceneImagePromptBuilder` class similar to `NarrationJobBuilder`
   - Consumes current scene data from `GameMemoryStore.get_context_for_prompt()`
   - Generates descriptive prompts optimized for visual scene generation
   - Template-driven approach using config files

3. **Scene Context for Image Generation**
    Strong focus on non-speculative facts, this is important to keep the scene llm prompt short and conducent to a rich, quality scene image mindful of local AI limitations.
   - Current room name and description
   - Visible items and their states
   - Actions and events that have taken place by player or otherwise, including how the player entered the scene.
   - The AI image generation prompt is created using LLM in a Configurable, Template-driven technique similar to the one used in the narration feature

#### Image Generation Pipeline

1. **SD-Server Integration**
   - **POST** `/v1/images/generations` endpoint
   - Content-Type: `application/json`
   - Async HTTP client for non-blocking requests
   - Error handling for 400/500 responses with structured error messages
   - Advanced parameters via XML embedding: `<sd_cpp_extra_args>{"steps": 10}</sd_cpp_extra_args>`

2. **Caching Strategy**
   - Generate cache key from scene identifier + description content hash
   - Check cache before making generation requests
   - Store both the image file and associated metadata (prompt, generation timestamp)
   - Cache invalidation when scene description significantly changes

#### UI Integration

1. **Pop-up Window Component**
   - Text area showing the generation prompt
   - Button controls for regeneration actions

2. **Trigger Mechanism**
   - Window opens upon launch with the Game logo as a placeholder (TBD)
   - Manual toggle trigger via hide button, keyboard shortcut or command using the existing mechanisms of the textual UX
   - Configurable auto-display settings

## Implementation Details for Next Developer

### Current Working Components

**1. Scene Image Prompt Builder** (`module/scene_image_prompt_builder.py`)
```python
# Usage example:
builder = SceneImagePromptBuilder(main_config)  # Needs main config for LLM settings
prompt_spec = builder.build_meta_prompt(memory_context=game_memory)
sd_prompt = await builder.generate_sd_prompt(memory_context=game_memory)
```

Key methods:
- `build_meta_prompt()` - Creates LLM instruction from game context
- `generate_sd_prompt()` - Calls LLM to get actual diffusion prompt
- Uses project's existing LLM client infrastructure
- Configuration-driven via `config/scene_image_prompt_template.json`

**2. SD-Server Client** (`module/sd_server_client.py`)
```python
# Usage example:
client = SDServerClient()
request = ImageGenerationRequest(prompt=sd_prompt, size="256x256", steps=4)
response = await client.generate_image(request)
```

Key features:
- Async HTTP with timeout handling (320s default)
- XML parameter embedding for advanced settings
- Structured error handling for network/API failures
- Base64 image data handling

**3. Scene Image Cache** (`module/scene_image_cache.py`)
```python
# Usage example:
cache = SceneImageCache()
cache.store_image(room_name, response, quality)  # Stores both image and metadata
image_data, metadata = cache.load_image(room_name, quality)
```

Key features:
- Multi-quality tracking per room in single JSON metadata file
- Quality-specific PNG files: `room_name_quality.png`
- Metadata format: `{"room_name": "...", "qualities": {"medium": {...}, "high": {...}}}`
- Only replaces specific quality on regeneration

**4. Scene Image Popup** (`module/scene_image_popup.py`)
```python
# Usage example (needs UI integration):
popup = SceneImagePopup(
    room_name="West of House",
    image_data=image_bytes,
    prompt_text="detailed pencil art...",
    on_regenerate=callback_function
)
```

Key features:
- Textual ModalScreen component
- Three action buttons with configurable callbacks
- Image display (currently shows metadata, not actual image)
- Non-modal interaction design

### Critical Integration Points

**1. Service Layer Update Needed** (`module/scene_image_service.py`)
Current service has placeholder TODO for LLM integration. Need to:
```python
# Replace this TODO in _generate_new_image():
# TODO: Call LLM with prompt_spec.meta_prompt to get diffusion prompt
diffusion_prompt = await self._prompt_builder.generate_sd_prompt(memory_context=job.memory_context)
```

**2. Main UI Integration** (`module/ui_helper.py`)
The popup widget exists but isn't connected to the main Textual app. Need to:
- Add popup state management to `IFBuddyTUI` class
- Handle popup show/hide via controller
- Add keyboard shortcuts for scene image commands

**3. Configuration Requirements**
- Main config must contain LLM provider settings for prompt generation
- Scene image config contains SD-server and quality settings
- Environment variables: `SD_SERVER_BASE_URL` for remote server

### Testing

**Current Test** (`testing/test_scene_prompt_builder.py`)
- Validates complete prompt generation pipeline
- Shows meta-prompt and final SD prompt
- Requires LLM server running (shows: "🟢 Service is Started on http://127.0.0.1:56338/")

**Additional Tests Needed**
- End-to-end service test with image generation
- Cache system stress testing
- UI popup integration testing

### Known Issues & Gotchas

1. **No Fallbacks**: Code follows Prime Directive #6 - fails cleanly if configuration missing
2. **Sync vs Async**: LLM client is synchronous, SD client is async
3. **Quality Parameters**: Quality affects SD generation (steps/size), not prompts
4. **Cache Structure**: Migrates old single-quality format to new multi-quality automatically

---

## Original Specification


### Phase 1: Core Infrastructure

1. **Scene Image Service**
   ```
   module/scene_image_service.py
   ```
   - `SceneImageService` class with async queue integration
   - `SceneImagePromptBuilder` for generating image prompts
   - Integration with existing LLM orchestration

2. **SD-Server Client**
   ```
   module/sd_server_client.py
   ```
   - Async HTTP client for sd-server REST API
   - Request format: `{"prompt": "scene_description", "size": "512x512", "n": 1}`
   - Response format: `{"data": [{"b64_json": "base64_image"}], "created": "timestamp"}`
   - Advanced parameters embedded in prompt via XML tags
   - Error handling for structured error responses

3. **Caching System**
   ```
   module/scene_image_cache.py
   ```
   - File-based caching in `res/scene-img/`
   - Cache key based on scene identifier
   - Metadata storage: `{"prompt": "clean_prompt", "size": "512x512", "steps": 10, "created": "timestamp"}`
   - Base64 to PNG file conversion and storage

### Phase 2: UI Components

4. **Pop-up Window Widget**
   ```
   module/scene_image_popup.py
   ```
   - Textual-based modal/overlay component
   - Image display handling (ASCII conversion for terminal)
   - Interactive buttons and event handling

5. **UI Integration**
   - Modify `module/ui_helper.py` to support pop-up overlay
   - Add keyboard shortcuts and commands
   - Integration with main game controller

### Phase 3: Configuration & Integration

6. **Configuration Schema**
   ```
   config/scene_image_config.json
   config/scene_image_prompt_template.json
   ```
   - SD-server connection settings
   - Image generation parameters
   - Prompt templates and context building rules
   - Caching configuration

7. **Queue Integration**
   - Modify existing LLM orchestration to include scene image jobs
   - Priority and scheduling logic
   - Integration with `common_llm_layer.py`

## Configuration

### SD-Server Settings
```json
{
  "sd_server_base_url": "http://localhost:7860",
  "sd_server_timeout": 90,
  "default_size": "256x256",
  "output_format": "png",
  "generation_steps": 10,
}
```

### Scene Image Prompt Template
```json
{
  "scene_template": "Create a brief, concise but effective AI diffusion prompt that will generate: A detailed pencil art illustration intented to describe an interactive fiction scene titled {room_name}, with description elements {description}, visible items {visible_items}, {playername} entered the scene by {enteringaction} and here are the most recent events {shortevents}, the prompt must be less than 120 characters so use your token real estate wisely.",
}
```
## User Experience

### Automatic Generation
1. Player enters a new room or significant scene change occurs
1.1 Medium Quality by default, for quicker inference
2. If no cached scene image, Scene image generation is queued so that it follows up after text scene narration completes, 
3. Image generation happens in background
4. Pop-up automatically appears when image is ready (configurable)

### Manual Interaction
1. Player can trigger scene image generation via hotkey or the thumbs-down button
2. Pop-up can be opened/closed without interrupting game

### Regeneration Workflow
1. **Prompt Regeneration**: 
   - Thumbs-down triggers new LLM call for better prompt
   - Uses current scene context (may have updated), or the player simply didnt appreciate the illustration
   - Automatically triggers follow-up new image generation queuing

2. **Image Regeneration**:
   - Uses existing prompt but calls sd-server for new image, highest quality (diffusion steps)
   - Default Quality and High quality n steps configured via config json
   - Faster than full prompt regeneration

## Error Handling

### LLM and Image Failures
- Fallback to basic scene description if prompt generation fails
- Fallback to logo image when no cached or generated image to display
- Retry logic is only manual, queued

### Image Generation Failures
- Graceful degradation to text-only display
- User-friendly error messages in pop-up

## Observability

### Logging
Follow same Logging strategy as rest of the app
- Scene image generation requests and responses
- Cache hit/miss statistics
- Generation timing and performance metrics
- Error tracking and debugging information

### JSONL Logs
```
scene_image_generation.jsonl
```
- Structured logging following project patterns
- Generation metadata, prompts, and results
- Performance and caching analytics

## Future Enhancements

### Advanced Features
- Leverage idle time to queue higher quality, same-seed images of scenes with only low quality
- Leverage idle time to queue low-quality images for Scenes that yet do not have an image