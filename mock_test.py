class MockLLM:
    
    def generate(self, prompt: str) -> str:
        
        if "PCR" in prompt:
            return "Step 1: Add buffer\nStep 2: Add DNA"
        
        elif "invalid" in prompt:
            return "Add 1000ml to well"
        
        return "Unknown protocol"