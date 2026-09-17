LIST primeNumbers = p2 = 2, p3 = 3, p5 = 5, p7 = 7, p11 = 11, p13 = 13, p17 = 17, p19 = 19, p23 = 23
LIST Nums = one, two, three, four, five
Doc: {LIST_RANGE(LIST_ALL(primeNumbers), 10, 20)}
Clamp: {LIST_RANGE(LIST_ALL(Nums), -5, 99)}
Empty: {LIST_RANGE(LIST_ALL(Nums), 40, 50)}
MinItem: {LIST_RANGE(LIST_ALL(Nums), two, four)}
FromInt: {Nums(3)}
FromIntBad: {Nums(99)}
-> END
