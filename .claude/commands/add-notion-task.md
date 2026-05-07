# Add Task to Notion

Add a new task to the Notion workspace using the New Task template.

## Arguments
$ARGUMENTS

## Instructions

You are adding a task to the user's Notion workspace. Follow these steps exactly.

### Step 1 — Collect parameters

If $ARGUMENTS is empty or missing any of the four required fields, ask the user for them before proceeding:

- **Task name** — what is the task called?
- **Area** — which area does it belong to? (e.g. "Home", "Workplace - IDE", "Personal Life")
- **Project** — which project does it belong to? (type "none" if no project)
- **Due date** — when is it due? (accept natural language like "this Saturday", "next Monday", "May 30" and convert to YYYY-MM-DD)

Do not proceed until all four fields are confirmed.

### Step 2 — Find the Area page URL

Search the Area database for the area name the user provided:

- Use `mcp__claude_ai_Notion__notion-search` with the area name as the query and `data_source_url` set to `collection://2849aa0c-f135-81e0-85a8-000becb42041`
- Pick the best matching result and use its URL
- If no match is found, tell the user and ask them to clarify the area name

### Step 3 — Find the Project page URL

If the user specified a project (not "none"):

- Use `mcp__claude_ai_Notion__notion-search` with the project name as the query and `data_source_url` set to `collection://2849aa0c-f135-81b1-aeeb-000baf09af87`
- If a matching project is found, use its URL
- If no matching project is found, ask the user: "Project '[name]' doesn't exist yet. Should I create it?" — if yes, create it using `mcp__claude_ai_Notion__notion-create-pages` in the projects data source (`collection://2849aa0c-f135-81b1-aeeb-000baf09af87`) with template ID `2849aa0c-f135-81e5-bc55-f8d7e9d5a0f3`, then use the new page URL

### Step 4 — Create the task

Call `mcp__claude_ai_Notion__notion-create-pages` with:

```
parent:
  type: data_source_id
  data_source_id: 2849aa0c-f135-81f5-b051-000b6827d73f

pages:
  - template_id: 2849aa0c-f135-818a-aa83-fdc5138759c8
    properties:
      Task name: <task name>
      area (1): ["<area page URL>"]
      projects (1): ["<project page URL>"]   ← omit if user said "none"
      date:Due:start: <YYYY-MM-DD>
      date:Due:is_datetime: 0
      Status: "🍵"
```

### Step 5 — Confirm

After the task is created, tell the user:
- Task name
- Area assigned
- Project assigned (or "No project")
- Due date
- Link to the task page URL returned by Notion

## Key IDs (do not modify)

| Resource | ID |
|---|---|
| Tasks data source | `2849aa0c-f135-81f5-b051-000b6827d73f` |
| New Task template | `2849aa0c-f135-818a-aa83-fdc5138759c8` |
| Area data source | `collection://2849aa0c-f135-81e0-85a8-000becb42041` |
| Projects data source | `collection://2849aa0c-f135-81b1-aeeb-000baf09af87` |
| New Project template | `2849aa0c-f135-81e5-bc55-f8d7e9d5a0f3` |
