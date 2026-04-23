import re

class PatternDetector:
    """
    Centralizado detector de patrones de User Stories multilenguaje.
    Soporta: EN, ES, CA con sus variantes.
    """
    
    # Patrones regex compilados para optimización
    PATTERNS = [
        # English
        r"\bas\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+\s+i\s+want\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+\s+so\s+that\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+",
        r"\bas\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+\s+i\s+want\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+\s+to\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+",
        
        # Spanish - COMO...QUIERO...
        r"\bcomo\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+\s+quiero\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+\s+(?:de\s+manera\s+que|de\s+forma\s+que|para|por|porqu[eé]|porque)\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+",
        
        # Catalan - COM...VULL...
        r"\bcom\s+(?:a\s+)?[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+\s+vull\s+[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+\s+(?:de\s+manera\s+que|de\s+forma\s+que|per\s+a\s+poder|per\s+poder|per\s+tal\s+de|per\s+tal\s+d[’']|per|perqu[eè]|perqué)\s*[\w\s'àáäâäèéëêìíïîòóöôùúüûñçÀÁÄÂÈÉËÊÌÍÏÎÒÓÖÔÙÚÜÛÑÇ’()\/·,.:;!?-]+",
    ]
    
    # Compilar patrones una sola vez
    _compiled_patterns = [re.compile(p, re.IGNORECASE) for p in PATTERNS]
    
    @classmethod
    def detect_pattern(cls, description: str) -> bool:
        """
        Detecta si una descripción contiene alguno de los patrones BDD soportados.
        
        Args:
            description: Texto de descripción de user story
            
        Returns:
            bool: True si contiene patrón válido, False en caso contrario
        """
        if not description or not isinstance(description, str):
            return False
        
        # Normalizar: eliminar saltos de línea excesivos, mantener separadores
        normalized = ' '.join(description.split())
        
        # Probar cada patrón
        for pattern in cls._compiled_patterns:
            if pattern.search(normalized):
                return True
        
        return False