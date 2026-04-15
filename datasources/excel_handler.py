from datetime import datetime


# List of activity types extracted from the Excel sheet
ACTIVITY_TYPES = [
    "Reunió d'equip",
    "Reunió focal",
    "Classe passiva",
    "Formació",
    "Desenvolupament",
    "Gestió de projecte",
    "Documentació",
    "Presentació"
]

def parse_excel_event(raw_payload: dict, prj, quality_model) -> dict:
    '''
    Function to parse the payload from the Excel webhook and return a dict with the data
    '''
    # Receive the paraemters from the API query
    quality_model = quality_model
    
    # Get the values from the payload
    ts       = raw_payload.get("timestamp")
    iteration= raw_payload.get("iteration")
    date     = raw_payload.get("date")
    duration = raw_payload.get("duration")
    activity = raw_payload.get("activity")
    comment  = raw_payload.get("comment")
    epic     = raw_payload.get("epic")
    members  = raw_payload.get("members", [])
    hours    = raw_payload.get("memberHours", [])
    config   = raw_payload.get("configRange", [])


    # Clean the members list, sometimes there are empty strings 
    members_clean = [m.strip() for m in members if isinstance(m, str) and m.strip()]
    # Pair the members with their hours, if there are more members than hours, we will ignore the extra members
    hours_clean   = hours[:len(members_clean)]

    # Create a dictionary with the members and their hours
    members_dict = {
        f"hours_{member}": hours_clean[idx]
        for idx, member in enumerate(members_clean)
    }

    # Map the activity types to the configRange values
    activity_hours = {}
    for idx, activity_name in enumerate(ACTIVITY_TYPES):
        # Pick the value from the configRange, if it exists, otherwise set it to 0
        val = config[idx] if idx < len(config) and config[idx] is not None else 0
        key = f"hours_{activity_name.replace(' ', '_')}"
        activity_hours[key] = val

    # Sum the hours for each activity type
    total_hours = sum(activity_hours.values())
    
    

    # Finally, return a dict containing the full structure
    return {
        "timestamp":       ts,
        "team":            prj,
        "quality_model":   quality_model,
        "iteration":       iteration,
        "activity_date":   date,
        "duration_h":      duration,
        "activity_type":   activity,
        "comment":         comment,
        "epic":            epic,
        "members":         members_clean,
        **members_dict,
        **activity_hours,
        "total_hours":     total_hours
    }


