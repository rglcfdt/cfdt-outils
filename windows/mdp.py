import bcrypt

mot_de_passe = "CFDTaccompagnement2026!"

# Génération du hash
hash_mdp = bcrypt.hashpw(
    mot_de_passe.encode("utf-8"),
    bcrypt.gensalt(rounds=12)
)

print(hash_mdp.decode())