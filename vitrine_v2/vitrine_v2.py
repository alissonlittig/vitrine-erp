# Lançador da demo: python vitrine_v2/vitrine_v2.py --pasta-dados <pasta> --origem <demo_centro.db>
import app
from lojas import FILIAIS

if __name__ == "__main__":
    app.main(FILIAIS["centro"])
