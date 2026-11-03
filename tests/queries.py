"""Customer questions with the manual sections that may answer them (shared by offline and live tests)."""
QUERIES = {
    "Qual o horário de funcionamento?": {"2"},
    "Posso parcelar em 10x?": {"3.1", "3"},
    "Me arrependi da compra, posso devolver?": {"4.1"},
    "O violão veio com defeito": {"4.2", "8.1"},
    "Vocês vendem cordas e palhetas?": {"1", "7.1"},
    "Qual a garantia dos produtos?": {"8.1", "8.2"},
    "Quanto é o frete para Dourados?": {"5.2"},
    "Frete grátis acima de quanto?": {"5.1"},
    "Como rastrear meu pedido?": {"5.3"},
    "Tem desconto no PIX?": {"3", "6.2"},
    "Quero reclamar do atendimento": {"7.3"},
    "Vocês compartilham meus dados?": {"9"},
    "Quando é a Black Friday?": {"6.1"},
    "Posso trocar a cor do instrumento?": {"4.3"},
    "Posso devolver a boquilha do sax?": {"4.4"},
    "O desconto da promoção acumula com o PIX?": {"6.2"},
    "Qual o endereço da loja?": {"1.2"},
    "A garantia cobre queda?": {"8.3", "4.2"},
}

# Paraphrases with little word overlap with the manual: where semantic search must earn its place.
HARD_QUERIES = {
    "Dá pra pagar em várias vezes no cartão?": {"3", "3.1"},
    "O instrumento chegou quebrado, e agora?": {"5.2"},
    "Vocês abrem aos domingos?": {"2"},
    "Quanto tempo demora a entrega aqui em Campo Grande?": {"5.1"},
    "Posso pagar metade no pix e metade no cartão?": {"3.1"},
    "Comprei ontem e já não quero mais": {"4.1"},
    "Vocês têm um parceiro que venda palheta?": {"7.1", "1"},
    "Meus dados pessoais ficam seguros com vocês?": {"9"},
    "Fiz o pedido e não recebi o código para acompanhar": {"5.3"},
    "Tem algum desconto se eu pagar à vista?": {"3", "6.2"},
}
