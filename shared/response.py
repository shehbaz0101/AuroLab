def success_response(data = None, message = "Success"):
    return {
        "status" : "Success",
        "data" : data,
        "message" : message
    }
    
def error_response(message = "Error", errors = None):
    return {
        "status" :"error",
        "message" : message,
        "error" : errors or []
    }