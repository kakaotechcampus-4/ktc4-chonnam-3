"""Pure turn rules over BE-confirmed records; no persistence or session authority."""

from devon_ai import contracts as c

PERSONAS: tuple[c.PersonaId, ...] = ("tech_lead", "hr_manager", "domain_lead")


def allowed_personas(presented: tuple[c.PersonaId, ...]) -> tuple[c.PersonaId, ...]:
    """Keep exactly the choices that can still meet both minima in nine questions.

    Six technical turns is a Director target, not an extra minimum or fixed order.
    An already impossible input fails closed instead of rewriting past Personas.
    """
    c._convert(tuple[c.PersonaId, ...], presented, "presented personas", wire=False)
    count = len(presented)
    if count > 9 or (presented and presented[0] != "hr_manager"):
        raise c.ContractError("semantic", "question count or first persona")
    tech = presented.count("tech_lead")
    other = count - tech
    if max(0, 5 - tech) + max(0, 3 - other) > 9 - count:
        raise c.ContractError("semantic", "impossible persona distribution")
    if count == 9:
        return ()
    if count == 0:
        return ("hr_manager",)
    return tuple(
        persona
        for persona in PERSONAS
        if max(0, 5 - tech - (persona == "tech_lead"))
        + max(0, 3 - other - (persona != "tech_lead"))
        <= 8 - count
    )
