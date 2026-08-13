def allocate(basket, categories):
    share = {row["id"]: float(row["weight"]) for row in categories}
    count = {}
    for item in basket:
        group = item["group"]
        count[group] = count.get(group, 0) + 1
    output = []
    for item in basket:
        row = dict(item)
        row["weight"] = share[item["group"]] / count[item["group"]]
        output.append(row)
    return output
