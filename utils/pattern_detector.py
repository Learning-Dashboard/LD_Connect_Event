import re

class PatternDetector:
    """
    Centralizado detector de patrones de User Stories multilenguaje.
    Soporta: EN, ES, CA con sus variantes.
    """
    
    # Patrones regex compilados para optimización
    PATTERNS = [
        # English
        r"\bas\s+[\w\s]+\s+i\s+want\s+[\w\s,.:;!?-]+\s+so\s+that\s+[\w\s,.:;!?-]+",
        r"\bas\s+[\w\s]+\s+i\s+want\s+[\w\s,.:;!?-]+\s+to\s+[\w\s,.:;!?-]+",
        
        # Spanish - COMO...QUIERO...
        r"\bcomo\s+[\w\s]+\s+quiero\s+[\w\s,.:;!?-]+\s+(?:de\s+manera\s+que|de\s+forma\s+que|para|por|porqu[eé]|porque)\s+[\w\s,.:;!?-]+",
        
        # Catalan - COM...VULL...
        r"\bcom\s+[\w\s]+\s+vull\s+[\w\s,.:;!?-]+\s+(?:de\s+manera\s+que|de\s+forma\s+que|per|perqu[eè]|perqué)\s+[\w\s,.:;!?-]+",
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