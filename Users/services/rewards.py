def add_score(user, score: int):
    if score <= 0:
        return

    user.total_score += score
    user.save(update_fields=["total_score"])

def calculate_score_from_fee(fee: int) -> int:
    if not fee or fee < 100_000:
        return 0

    return (fee // 100_000) * 5

