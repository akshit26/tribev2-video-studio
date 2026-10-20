"""Keep prompt-specific attempts so a retry cannot erase a reusable result."""
import copy


class CompletionCache:
    def __init__(self, checkpoint, signature):
        self.signature = signature
        matching = checkpoint if checkpoint.get("signature") == signature else {}
        self.parts = copy.deepcopy(matching.get("parts", {}))
        self.variants = copy.deepcopy(matching.get("variants", {}))
        for label, part in self.parts.items():
            if part.get("prompt_hash"):
                self.variants.setdefault(label, {})[part["prompt_hash"]] = copy.deepcopy(part)

    def get(self, label, prompt_hash):
        part = self.variants.get(label, {}).get(prompt_hash)
        return copy.deepcopy(part) if part is not None else None

    def remember(self, label, prompt_hash, result):
        part = {"prompt_hash": prompt_hash, "result": copy.deepcopy(result)}
        self.parts[label] = part
        self.variants.setdefault(label, {})[prompt_hash] = copy.deepcopy(part)

    def reject(self,label,prompt_hash):
        variants=self.variants.get(label,{})
        variants.pop(prompt_hash,None)
        if not variants:self.variants.pop(label,None)
        if self.parts.get(label,{}).get('prompt_hash')==prompt_hash:
            self.parts.pop(label,None)
            if variants:self.parts[label]=copy.deepcopy(next(reversed(variants.values())))

    def snapshot(self):
        return {"signature": self.signature, "parts": self.parts, "variants": self.variants}
