# this module initializes, and incrementally builds the memory structures from the game meta-progress 
## it tracks the basic 'player name' sessions, based on either the default player name or when the player changes her/his name
## uses tinydb for game object memory and for game meta-progress data
## it takes care of getting game controller inputs, heuristically parse into structuring game elements memory
## it reads the designed ai buddy memory structure json
## It prepares the prompts for OpenAi Structured Output inference
## It prepares the prompts for AI buddy narration inference
## it parses the output from AI streams into game memory structures
