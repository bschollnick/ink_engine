// Generated structural fixture. Breadth over prose: every construct that
// affects how containers nest, so path strings are exercised at scale.
LIST Flags = alpha, beta, gamma, delta, epsilon
VAR flags = ()
VAR counter = 0
-> region_0

=== region_0 ===
Region 0.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_0.hall
+ {counter >= 0} [Guarded path] -> region_0.guarded
+ [Tunnel out] -> side_0 -> region_0.after_tunnel
* [Once only] -> region_0.hall
- (gathered_0) -> region_1
= hall
<- ambience_0
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_0) ~ counter += 1
  -> region_1
= guarded
~ flags += beta
Guarded stitch 0.
-> region_1
= after_tunnel
Returned from tunnel 0.
-> region_1

=== side_0 ===
Side content 0.
->->

=== ambience_0 ===
+ [Listen 0] -> DONE

=== region_1 ===
Region 1.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_1.hall
+ {counter >= 0} [Guarded path] -> region_1.guarded
+ [Tunnel out] -> side_1 -> region_1.after_tunnel
* [Once only] -> region_1.hall
- (gathered_1) -> region_2
= hall
<- ambience_1
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_1) ~ counter += 1
  -> region_2
= guarded
~ flags += beta
Guarded stitch 1.
-> region_2
= after_tunnel
Returned from tunnel 1.
-> region_2

=== side_1 ===
Side content 1.
->->

=== ambience_1 ===
+ [Listen 1] -> DONE

=== region_2 ===
Region 2.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_2.hall
+ {counter >= 0} [Guarded path] -> region_2.guarded
+ [Tunnel out] -> side_2 -> region_2.after_tunnel
* [Once only] -> region_2.hall
- (gathered_2) -> region_3
= hall
<- ambience_2
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_2) ~ counter += 1
  -> region_3
= guarded
~ flags += beta
Guarded stitch 2.
-> region_3
= after_tunnel
Returned from tunnel 2.
-> region_3

=== side_2 ===
Side content 2.
->->

=== ambience_2 ===
+ [Listen 2] -> DONE

=== region_3 ===
Region 3.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_3.hall
+ {counter >= 0} [Guarded path] -> region_3.guarded
+ [Tunnel out] -> side_3 -> region_3.after_tunnel
* [Once only] -> region_3.hall
- (gathered_3) -> region_4
= hall
<- ambience_3
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_3) ~ counter += 1
  -> region_4
= guarded
~ flags += beta
Guarded stitch 3.
-> region_4
= after_tunnel
Returned from tunnel 3.
-> region_4

=== side_3 ===
Side content 3.
->->

=== ambience_3 ===
+ [Listen 3] -> DONE

=== region_4 ===
Region 4.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_4.hall
+ {counter >= 0} [Guarded path] -> region_4.guarded
+ [Tunnel out] -> side_4 -> region_4.after_tunnel
* [Once only] -> region_4.hall
- (gathered_4) -> region_5
= hall
<- ambience_4
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_4) ~ counter += 1
  -> region_5
= guarded
~ flags += beta
Guarded stitch 4.
-> region_5
= after_tunnel
Returned from tunnel 4.
-> region_5

=== side_4 ===
Side content 4.
->->

=== ambience_4 ===
+ [Listen 4] -> DONE

=== region_5 ===
Region 5.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_5.hall
+ {counter >= 0} [Guarded path] -> region_5.guarded
+ [Tunnel out] -> side_5 -> region_5.after_tunnel
* [Once only] -> region_5.hall
- (gathered_5) -> region_6
= hall
<- ambience_5
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_5) ~ counter += 1
  -> region_6
= guarded
~ flags += beta
Guarded stitch 5.
-> region_6
= after_tunnel
Returned from tunnel 5.
-> region_6

=== side_5 ===
Side content 5.
->->

=== ambience_5 ===
+ [Listen 5] -> DONE

=== region_6 ===
Region 6.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_6.hall
+ {counter >= 0} [Guarded path] -> region_6.guarded
+ [Tunnel out] -> side_6 -> region_6.after_tunnel
* [Once only] -> region_6.hall
- (gathered_6) -> region_7
= hall
<- ambience_6
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_6) ~ counter += 1
  -> region_7
= guarded
~ flags += beta
Guarded stitch 6.
-> region_7
= after_tunnel
Returned from tunnel 6.
-> region_7

=== side_6 ===
Side content 6.
->->

=== ambience_6 ===
+ [Listen 6] -> DONE

=== region_7 ===
Region 7.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_7.hall
+ {counter >= 0} [Guarded path] -> region_7.guarded
+ [Tunnel out] -> side_7 -> region_7.after_tunnel
* [Once only] -> region_7.hall
- (gathered_7) -> region_8
= hall
<- ambience_7
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_7) ~ counter += 1
  -> region_8
= guarded
~ flags += beta
Guarded stitch 7.
-> region_8
= after_tunnel
Returned from tunnel 7.
-> region_8

=== side_7 ===
Side content 7.
->->

=== ambience_7 ===
+ [Listen 7] -> DONE

=== region_8 ===
Region 8.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_8.hall
+ {counter >= 0} [Guarded path] -> region_8.guarded
+ [Tunnel out] -> side_8 -> region_8.after_tunnel
* [Once only] -> region_8.hall
- (gathered_8) -> region_9
= hall
<- ambience_8
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_8) ~ counter += 1
  -> region_9
= guarded
~ flags += beta
Guarded stitch 8.
-> region_9
= after_tunnel
Returned from tunnel 8.
-> region_9

=== side_8 ===
Side content 8.
->->

=== ambience_8 ===
+ [Listen 8] -> DONE

=== region_9 ===
Region 9.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_9.hall
+ {counter >= 0} [Guarded path] -> region_9.guarded
+ [Tunnel out] -> side_9 -> region_9.after_tunnel
* [Once only] -> region_9.hall
- (gathered_9) -> region_10
= hall
<- ambience_9
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_9) ~ counter += 1
  -> region_10
= guarded
~ flags += beta
Guarded stitch 9.
-> region_10
= after_tunnel
Returned from tunnel 9.
-> region_10

=== side_9 ===
Side content 9.
->->

=== ambience_9 ===
+ [Listen 9] -> DONE

=== region_10 ===
Region 10.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_10.hall
+ {counter >= 0} [Guarded path] -> region_10.guarded
+ [Tunnel out] -> side_10 -> region_10.after_tunnel
* [Once only] -> region_10.hall
- (gathered_10) -> region_11
= hall
<- ambience_10
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_10) ~ counter += 1
  -> region_11
= guarded
~ flags += beta
Guarded stitch 10.
-> region_11
= after_tunnel
Returned from tunnel 10.
-> region_11

=== side_10 ===
Side content 10.
->->

=== ambience_10 ===
+ [Listen 10] -> DONE

=== region_11 ===
Region 11.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_11.hall
+ {counter >= 0} [Guarded path] -> region_11.guarded
+ [Tunnel out] -> side_11 -> region_11.after_tunnel
* [Once only] -> region_11.hall
- (gathered_11) -> region_12
= hall
<- ambience_11
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_11) ~ counter += 1
  -> region_12
= guarded
~ flags += beta
Guarded stitch 11.
-> region_12
= after_tunnel
Returned from tunnel 11.
-> region_12

=== side_11 ===
Side content 11.
->->

=== ambience_11 ===
+ [Listen 11] -> DONE

=== region_12 ===
Region 12.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_12.hall
+ {counter >= 0} [Guarded path] -> region_12.guarded
+ [Tunnel out] -> side_12 -> region_12.after_tunnel
* [Once only] -> region_12.hall
- (gathered_12) -> region_13
= hall
<- ambience_12
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_12) ~ counter += 1
  -> region_13
= guarded
~ flags += beta
Guarded stitch 12.
-> region_13
= after_tunnel
Returned from tunnel 12.
-> region_13

=== side_12 ===
Side content 12.
->->

=== ambience_12 ===
+ [Listen 12] -> DONE

=== region_13 ===
Region 13.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_13.hall
+ {counter >= 0} [Guarded path] -> region_13.guarded
+ [Tunnel out] -> side_13 -> region_13.after_tunnel
* [Once only] -> region_13.hall
- (gathered_13) -> region_14
= hall
<- ambience_13
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_13) ~ counter += 1
  -> region_14
= guarded
~ flags += beta
Guarded stitch 13.
-> region_14
= after_tunnel
Returned from tunnel 13.
-> region_14

=== side_13 ===
Side content 13.
->->

=== ambience_13 ===
+ [Listen 13] -> DONE

=== region_14 ===
Region 14.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_14.hall
+ {counter >= 0} [Guarded path] -> region_14.guarded
+ [Tunnel out] -> side_14 -> region_14.after_tunnel
* [Once only] -> region_14.hall
- (gathered_14) -> region_15
= hall
<- ambience_14
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_14) ~ counter += 1
  -> region_15
= guarded
~ flags += beta
Guarded stitch 14.
-> region_15
= after_tunnel
Returned from tunnel 14.
-> region_15

=== side_14 ===
Side content 14.
->->

=== ambience_14 ===
+ [Listen 14] -> DONE

=== region_15 ===
Region 15.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_15.hall
+ {counter >= 0} [Guarded path] -> region_15.guarded
+ [Tunnel out] -> side_15 -> region_15.after_tunnel
* [Once only] -> region_15.hall
- (gathered_15) -> region_16
= hall
<- ambience_15
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_15) ~ counter += 1
  -> region_16
= guarded
~ flags += beta
Guarded stitch 15.
-> region_16
= after_tunnel
Returned from tunnel 15.
-> region_16

=== side_15 ===
Side content 15.
->->

=== ambience_15 ===
+ [Listen 15] -> DONE

=== region_16 ===
Region 16.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_16.hall
+ {counter >= 0} [Guarded path] -> region_16.guarded
+ [Tunnel out] -> side_16 -> region_16.after_tunnel
* [Once only] -> region_16.hall
- (gathered_16) -> region_17
= hall
<- ambience_16
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_16) ~ counter += 1
  -> region_17
= guarded
~ flags += beta
Guarded stitch 16.
-> region_17
= after_tunnel
Returned from tunnel 16.
-> region_17

=== side_16 ===
Side content 16.
->->

=== ambience_16 ===
+ [Listen 16] -> DONE

=== region_17 ===
Region 17.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_17.hall
+ {counter >= 0} [Guarded path] -> region_17.guarded
+ [Tunnel out] -> side_17 -> region_17.after_tunnel
* [Once only] -> region_17.hall
- (gathered_17) -> region_18
= hall
<- ambience_17
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_17) ~ counter += 1
  -> region_18
= guarded
~ flags += beta
Guarded stitch 17.
-> region_18
= after_tunnel
Returned from tunnel 17.
-> region_18

=== side_17 ===
Side content 17.
->->

=== ambience_17 ===
+ [Listen 17] -> DONE

=== region_18 ===
Region 18.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_18.hall
+ {counter >= 0} [Guarded path] -> region_18.guarded
+ [Tunnel out] -> side_18 -> region_18.after_tunnel
* [Once only] -> region_18.hall
- (gathered_18) -> region_19
= hall
<- ambience_18
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_18) ~ counter += 1
  -> region_19
= guarded
~ flags += beta
Guarded stitch 18.
-> region_19
= after_tunnel
Returned from tunnel 18.
-> region_19

=== side_18 ===
Side content 18.
->->

=== ambience_18 ===
+ [Listen 18] -> DONE

=== region_19 ===
Region 19.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_19.hall
+ {counter >= 0} [Guarded path] -> region_19.guarded
+ [Tunnel out] -> side_19 -> region_19.after_tunnel
* [Once only] -> region_19.hall
- (gathered_19) -> region_20
= hall
<- ambience_19
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_19) ~ counter += 1
  -> region_20
= guarded
~ flags += beta
Guarded stitch 19.
-> region_20
= after_tunnel
Returned from tunnel 19.
-> region_20

=== side_19 ===
Side content 19.
->->

=== ambience_19 ===
+ [Listen 19] -> DONE

=== region_20 ===
Region 20.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_20.hall
+ {counter >= 0} [Guarded path] -> region_20.guarded
+ [Tunnel out] -> side_20 -> region_20.after_tunnel
* [Once only] -> region_20.hall
- (gathered_20) -> region_21
= hall
<- ambience_20
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_20) ~ counter += 1
  -> region_21
= guarded
~ flags += beta
Guarded stitch 20.
-> region_21
= after_tunnel
Returned from tunnel 20.
-> region_21

=== side_20 ===
Side content 20.
->->

=== ambience_20 ===
+ [Listen 20] -> DONE

=== region_21 ===
Region 21.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_21.hall
+ {counter >= 0} [Guarded path] -> region_21.guarded
+ [Tunnel out] -> side_21 -> region_21.after_tunnel
* [Once only] -> region_21.hall
- (gathered_21) -> region_22
= hall
<- ambience_21
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_21) ~ counter += 1
  -> region_22
= guarded
~ flags += beta
Guarded stitch 21.
-> region_22
= after_tunnel
Returned from tunnel 21.
-> region_22

=== side_21 ===
Side content 21.
->->

=== ambience_21 ===
+ [Listen 21] -> DONE

=== region_22 ===
Region 22.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_22.hall
+ {counter >= 0} [Guarded path] -> region_22.guarded
+ [Tunnel out] -> side_22 -> region_22.after_tunnel
* [Once only] -> region_22.hall
- (gathered_22) -> region_23
= hall
<- ambience_22
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_22) ~ counter += 1
  -> region_23
= guarded
~ flags += beta
Guarded stitch 22.
-> region_23
= after_tunnel
Returned from tunnel 22.
-> region_23

=== side_22 ===
Side content 22.
->->

=== ambience_22 ===
+ [Listen 22] -> DONE

=== region_23 ===
Region 23.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_23.hall
+ {counter >= 0} [Guarded path] -> region_23.guarded
+ [Tunnel out] -> side_23 -> region_23.after_tunnel
* [Once only] -> region_23.hall
- (gathered_23) -> region_24
= hall
<- ambience_23
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_23) ~ counter += 1
  -> region_24
= guarded
~ flags += beta
Guarded stitch 23.
-> region_24
= after_tunnel
Returned from tunnel 23.
-> region_24

=== side_23 ===
Side content 23.
->->

=== ambience_23 ===
+ [Listen 23] -> DONE

=== region_24 ===
Region 24.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_24.hall
+ {counter >= 0} [Guarded path] -> region_24.guarded
+ [Tunnel out] -> side_24 -> region_24.after_tunnel
* [Once only] -> region_24.hall
- (gathered_24) -> region_25
= hall
<- ambience_24
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_24) ~ counter += 1
  -> region_25
= guarded
~ flags += beta
Guarded stitch 24.
-> region_25
= after_tunnel
Returned from tunnel 24.
-> region_25

=== side_24 ===
Side content 24.
->->

=== ambience_24 ===
+ [Listen 24] -> DONE

=== region_25 ===
Region 25.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_25.hall
+ {counter >= 0} [Guarded path] -> region_25.guarded
+ [Tunnel out] -> side_25 -> region_25.after_tunnel
* [Once only] -> region_25.hall
- (gathered_25) -> region_26
= hall
<- ambience_25
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_25) ~ counter += 1
  -> region_26
= guarded
~ flags += beta
Guarded stitch 25.
-> region_26
= after_tunnel
Returned from tunnel 25.
-> region_26

=== side_25 ===
Side content 25.
->->

=== ambience_25 ===
+ [Listen 25] -> DONE

=== region_26 ===
Region 26.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_26.hall
+ {counter >= 0} [Guarded path] -> region_26.guarded
+ [Tunnel out] -> side_26 -> region_26.after_tunnel
* [Once only] -> region_26.hall
- (gathered_26) -> region_27
= hall
<- ambience_26
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_26) ~ counter += 1
  -> region_27
= guarded
~ flags += beta
Guarded stitch 26.
-> region_27
= after_tunnel
Returned from tunnel 26.
-> region_27

=== side_26 ===
Side content 26.
->->

=== ambience_26 ===
+ [Listen 26] -> DONE

=== region_27 ===
Region 27.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_27.hall
+ {counter >= 0} [Guarded path] -> region_27.guarded
+ [Tunnel out] -> side_27 -> region_27.after_tunnel
* [Once only] -> region_27.hall
- (gathered_27) -> region_28
= hall
<- ambience_27
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_27) ~ counter += 1
  -> region_28
= guarded
~ flags += beta
Guarded stitch 27.
-> region_28
= after_tunnel
Returned from tunnel 27.
-> region_28

=== side_27 ===
Side content 27.
->->

=== ambience_27 ===
+ [Listen 27] -> DONE

=== region_28 ===
Region 28.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_28.hall
+ {counter >= 0} [Guarded path] -> region_28.guarded
+ [Tunnel out] -> side_28 -> region_28.after_tunnel
* [Once only] -> region_28.hall
- (gathered_28) -> region_29
= hall
<- ambience_28
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_28) ~ counter += 1
  -> region_29
= guarded
~ flags += beta
Guarded stitch 28.
-> region_29
= after_tunnel
Returned from tunnel 28.
-> region_29

=== side_28 ===
Side content 28.
->->

=== ambience_28 ===
+ [Listen 28] -> DONE

=== region_29 ===
Region 29.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_29.hall
+ {counter >= 0} [Guarded path] -> region_29.guarded
+ [Tunnel out] -> side_29 -> region_29.after_tunnel
* [Once only] -> region_29.hall
- (gathered_29) -> region_30
= hall
<- ambience_29
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_29) ~ counter += 1
  -> region_30
= guarded
~ flags += beta
Guarded stitch 29.
-> region_30
= after_tunnel
Returned from tunnel 29.
-> region_30

=== side_29 ===
Side content 29.
->->

=== ambience_29 ===
+ [Listen 29] -> DONE

=== region_30 ===
Region 30.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_30.hall
+ {counter >= 0} [Guarded path] -> region_30.guarded
+ [Tunnel out] -> side_30 -> region_30.after_tunnel
* [Once only] -> region_30.hall
- (gathered_30) -> region_31
= hall
<- ambience_30
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_30) ~ counter += 1
  -> region_31
= guarded
~ flags += beta
Guarded stitch 30.
-> region_31
= after_tunnel
Returned from tunnel 30.
-> region_31

=== side_30 ===
Side content 30.
->->

=== ambience_30 ===
+ [Listen 30] -> DONE

=== region_31 ===
Region 31.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_31.hall
+ {counter >= 0} [Guarded path] -> region_31.guarded
+ [Tunnel out] -> side_31 -> region_31.after_tunnel
* [Once only] -> region_31.hall
- (gathered_31) -> region_32
= hall
<- ambience_31
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_31) ~ counter += 1
  -> region_32
= guarded
~ flags += beta
Guarded stitch 31.
-> region_32
= after_tunnel
Returned from tunnel 31.
-> region_32

=== side_31 ===
Side content 31.
->->

=== ambience_31 ===
+ [Listen 31] -> DONE

=== region_32 ===
Region 32.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_32.hall
+ {counter >= 0} [Guarded path] -> region_32.guarded
+ [Tunnel out] -> side_32 -> region_32.after_tunnel
* [Once only] -> region_32.hall
- (gathered_32) -> region_33
= hall
<- ambience_32
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_32) ~ counter += 1
  -> region_33
= guarded
~ flags += beta
Guarded stitch 32.
-> region_33
= after_tunnel
Returned from tunnel 32.
-> region_33

=== side_32 ===
Side content 32.
->->

=== ambience_32 ===
+ [Listen 32] -> DONE

=== region_33 ===
Region 33.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_33.hall
+ {counter >= 0} [Guarded path] -> region_33.guarded
+ [Tunnel out] -> side_33 -> region_33.after_tunnel
* [Once only] -> region_33.hall
- (gathered_33) -> region_34
= hall
<- ambience_33
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_33) ~ counter += 1
  -> region_34
= guarded
~ flags += beta
Guarded stitch 33.
-> region_34
= after_tunnel
Returned from tunnel 33.
-> region_34

=== side_33 ===
Side content 33.
->->

=== ambience_33 ===
+ [Listen 33] -> DONE

=== region_34 ===
Region 34.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_34.hall
+ {counter >= 0} [Guarded path] -> region_34.guarded
+ [Tunnel out] -> side_34 -> region_34.after_tunnel
* [Once only] -> region_34.hall
- (gathered_34) -> region_35
= hall
<- ambience_34
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_34) ~ counter += 1
  -> region_35
= guarded
~ flags += beta
Guarded stitch 34.
-> region_35
= after_tunnel
Returned from tunnel 34.
-> region_35

=== side_34 ===
Side content 34.
->->

=== ambience_34 ===
+ [Listen 34] -> DONE

=== region_35 ===
Region 35.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_35.hall
+ {counter >= 0} [Guarded path] -> region_35.guarded
+ [Tunnel out] -> side_35 -> region_35.after_tunnel
* [Once only] -> region_35.hall
- (gathered_35) -> region_36
= hall
<- ambience_35
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_35) ~ counter += 1
  -> region_36
= guarded
~ flags += beta
Guarded stitch 35.
-> region_36
= after_tunnel
Returned from tunnel 35.
-> region_36

=== side_35 ===
Side content 35.
->->

=== ambience_35 ===
+ [Listen 35] -> DONE

=== region_36 ===
Region 36.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_36.hall
+ {counter >= 0} [Guarded path] -> region_36.guarded
+ [Tunnel out] -> side_36 -> region_36.after_tunnel
* [Once only] -> region_36.hall
- (gathered_36) -> region_37
= hall
<- ambience_36
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_36) ~ counter += 1
  -> region_37
= guarded
~ flags += beta
Guarded stitch 36.
-> region_37
= after_tunnel
Returned from tunnel 36.
-> region_37

=== side_36 ===
Side content 36.
->->

=== ambience_36 ===
+ [Listen 36] -> DONE

=== region_37 ===
Region 37.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_37.hall
+ {counter >= 0} [Guarded path] -> region_37.guarded
+ [Tunnel out] -> side_37 -> region_37.after_tunnel
* [Once only] -> region_37.hall
- (gathered_37) -> region_38
= hall
<- ambience_37
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_37) ~ counter += 1
  -> region_38
= guarded
~ flags += beta
Guarded stitch 37.
-> region_38
= after_tunnel
Returned from tunnel 37.
-> region_38

=== side_37 ===
Side content 37.
->->

=== ambience_37 ===
+ [Listen 37] -> DONE

=== region_38 ===
Region 38.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_38.hall
+ {counter >= 0} [Guarded path] -> region_38.guarded
+ [Tunnel out] -> side_38 -> region_38.after_tunnel
* [Once only] -> region_38.hall
- (gathered_38) -> region_39
= hall
<- ambience_38
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_38) ~ counter += 1
  -> region_39
= guarded
~ flags += beta
Guarded stitch 38.
-> region_39
= after_tunnel
Returned from tunnel 38.
-> region_39

=== side_38 ===
Side content 38.
->->

=== ambience_38 ===
+ [Listen 38] -> DONE

=== region_39 ===
Region 39.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_39.hall
+ {counter >= 0} [Guarded path] -> region_39.guarded
+ [Tunnel out] -> side_39 -> region_39.after_tunnel
* [Once only] -> region_39.hall
- (gathered_39) -> region_40
= hall
<- ambience_39
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_39) ~ counter += 1
  -> region_40
= guarded
~ flags += beta
Guarded stitch 39.
-> region_40
= after_tunnel
Returned from tunnel 39.
-> region_40

=== side_39 ===
Side content 39.
->->

=== ambience_39 ===
+ [Listen 39] -> DONE

=== region_40 ===
Region 40.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_40.hall
+ {counter >= 0} [Guarded path] -> region_40.guarded
+ [Tunnel out] -> side_40 -> region_40.after_tunnel
* [Once only] -> region_40.hall
- (gathered_40) -> region_41
= hall
<- ambience_40
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_40) ~ counter += 1
  -> region_41
= guarded
~ flags += beta
Guarded stitch 40.
-> region_41
= after_tunnel
Returned from tunnel 40.
-> region_41

=== side_40 ===
Side content 40.
->->

=== ambience_40 ===
+ [Listen 40] -> DONE

=== region_41 ===
Region 41.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_41.hall
+ {counter >= 0} [Guarded path] -> region_41.guarded
+ [Tunnel out] -> side_41 -> region_41.after_tunnel
* [Once only] -> region_41.hall
- (gathered_41) -> region_42
= hall
<- ambience_41
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_41) ~ counter += 1
  -> region_42
= guarded
~ flags += beta
Guarded stitch 41.
-> region_42
= after_tunnel
Returned from tunnel 41.
-> region_42

=== side_41 ===
Side content 41.
->->

=== ambience_41 ===
+ [Listen 41] -> DONE

=== region_42 ===
Region 42.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_42.hall
+ {counter >= 0} [Guarded path] -> region_42.guarded
+ [Tunnel out] -> side_42 -> region_42.after_tunnel
* [Once only] -> region_42.hall
- (gathered_42) -> region_43
= hall
<- ambience_42
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_42) ~ counter += 1
  -> region_43
= guarded
~ flags += beta
Guarded stitch 42.
-> region_43
= after_tunnel
Returned from tunnel 42.
-> region_43

=== side_42 ===
Side content 42.
->->

=== ambience_42 ===
+ [Listen 42] -> DONE

=== region_43 ===
Region 43.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_43.hall
+ {counter >= 0} [Guarded path] -> region_43.guarded
+ [Tunnel out] -> side_43 -> region_43.after_tunnel
* [Once only] -> region_43.hall
- (gathered_43) -> region_44
= hall
<- ambience_43
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_43) ~ counter += 1
  -> region_44
= guarded
~ flags += beta
Guarded stitch 43.
-> region_44
= after_tunnel
Returned from tunnel 43.
-> region_44

=== side_43 ===
Side content 43.
->->

=== ambience_43 ===
+ [Listen 43] -> DONE

=== region_44 ===
Region 44.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_44.hall
+ {counter >= 0} [Guarded path] -> region_44.guarded
+ [Tunnel out] -> side_44 -> region_44.after_tunnel
* [Once only] -> region_44.hall
- (gathered_44) -> region_45
= hall
<- ambience_44
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_44) ~ counter += 1
  -> region_45
= guarded
~ flags += beta
Guarded stitch 44.
-> region_45
= after_tunnel
Returned from tunnel 44.
-> region_45

=== side_44 ===
Side content 44.
->->

=== ambience_44 ===
+ [Listen 44] -> DONE

=== region_45 ===
Region 45.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_45.hall
+ {counter >= 0} [Guarded path] -> region_45.guarded
+ [Tunnel out] -> side_45 -> region_45.after_tunnel
* [Once only] -> region_45.hall
- (gathered_45) -> region_46
= hall
<- ambience_45
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_45) ~ counter += 1
  -> region_46
= guarded
~ flags += beta
Guarded stitch 45.
-> region_46
= after_tunnel
Returned from tunnel 45.
-> region_46

=== side_45 ===
Side content 45.
->->

=== ambience_45 ===
+ [Listen 45] -> DONE

=== region_46 ===
Region 46.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_46.hall
+ {counter >= 0} [Guarded path] -> region_46.guarded
+ [Tunnel out] -> side_46 -> region_46.after_tunnel
* [Once only] -> region_46.hall
- (gathered_46) -> region_47
= hall
<- ambience_46
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_46) ~ counter += 1
  -> region_47
= guarded
~ flags += beta
Guarded stitch 46.
-> region_47
= after_tunnel
Returned from tunnel 46.
-> region_47

=== side_46 ===
Side content 46.
->->

=== ambience_46 ===
+ [Listen 46] -> DONE

=== region_47 ===
Region 47.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_47.hall
+ {counter >= 0} [Guarded path] -> region_47.guarded
+ [Tunnel out] -> side_47 -> region_47.after_tunnel
* [Once only] -> region_47.hall
- (gathered_47) -> region_48
= hall
<- ambience_47
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_47) ~ counter += 1
  -> region_48
= guarded
~ flags += beta
Guarded stitch 47.
-> region_48
= after_tunnel
Returned from tunnel 47.
-> region_48

=== side_47 ===
Side content 47.
->->

=== ambience_47 ===
+ [Listen 47] -> DONE

=== region_48 ===
Region 48.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_48.hall
+ {counter >= 0} [Guarded path] -> region_48.guarded
+ [Tunnel out] -> side_48 -> region_48.after_tunnel
* [Once only] -> region_48.hall
- (gathered_48) -> region_49
= hall
<- ambience_48
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_48) ~ counter += 1
  -> region_49
= guarded
~ flags += beta
Guarded stitch 48.
-> region_49
= after_tunnel
Returned from tunnel 48.
-> region_49

=== side_48 ===
Side content 48.
->->

=== ambience_48 ===
+ [Listen 48] -> DONE

=== region_49 ===
Region 49.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_49.hall
+ {counter >= 0} [Guarded path] -> region_49.guarded
+ [Tunnel out] -> side_49 -> region_49.after_tunnel
* [Once only] -> region_49.hall
- (gathered_49) -> region_50
= hall
<- ambience_49
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_49) ~ counter += 1
  -> region_50
= guarded
~ flags += beta
Guarded stitch 49.
-> region_50
= after_tunnel
Returned from tunnel 49.
-> region_50

=== side_49 ===
Side content 49.
->->

=== ambience_49 ===
+ [Listen 49] -> DONE

=== region_50 ===
Region 50.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_50.hall
+ {counter >= 0} [Guarded path] -> region_50.guarded
+ [Tunnel out] -> side_50 -> region_50.after_tunnel
* [Once only] -> region_50.hall
- (gathered_50) -> region_51
= hall
<- ambience_50
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_50) ~ counter += 1
  -> region_51
= guarded
~ flags += beta
Guarded stitch 50.
-> region_51
= after_tunnel
Returned from tunnel 50.
-> region_51

=== side_50 ===
Side content 50.
->->

=== ambience_50 ===
+ [Listen 50] -> DONE

=== region_51 ===
Region 51.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_51.hall
+ {counter >= 0} [Guarded path] -> region_51.guarded
+ [Tunnel out] -> side_51 -> region_51.after_tunnel
* [Once only] -> region_51.hall
- (gathered_51) -> region_52
= hall
<- ambience_51
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_51) ~ counter += 1
  -> region_52
= guarded
~ flags += beta
Guarded stitch 51.
-> region_52
= after_tunnel
Returned from tunnel 51.
-> region_52

=== side_51 ===
Side content 51.
->->

=== ambience_51 ===
+ [Listen 51] -> DONE

=== region_52 ===
Region 52.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_52.hall
+ {counter >= 0} [Guarded path] -> region_52.guarded
+ [Tunnel out] -> side_52 -> region_52.after_tunnel
* [Once only] -> region_52.hall
- (gathered_52) -> region_53
= hall
<- ambience_52
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_52) ~ counter += 1
  -> region_53
= guarded
~ flags += beta
Guarded stitch 52.
-> region_53
= after_tunnel
Returned from tunnel 52.
-> region_53

=== side_52 ===
Side content 52.
->->

=== ambience_52 ===
+ [Listen 52] -> DONE

=== region_53 ===
Region 53.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_53.hall
+ {counter >= 0} [Guarded path] -> region_53.guarded
+ [Tunnel out] -> side_53 -> region_53.after_tunnel
* [Once only] -> region_53.hall
- (gathered_53) -> region_54
= hall
<- ambience_53
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_53) ~ counter += 1
  -> region_54
= guarded
~ flags += beta
Guarded stitch 53.
-> region_54
= after_tunnel
Returned from tunnel 53.
-> region_54

=== side_53 ===
Side content 53.
->->

=== ambience_53 ===
+ [Listen 53] -> DONE

=== region_54 ===
Region 54.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_54.hall
+ {counter >= 0} [Guarded path] -> region_54.guarded
+ [Tunnel out] -> side_54 -> region_54.after_tunnel
* [Once only] -> region_54.hall
- (gathered_54) -> region_55
= hall
<- ambience_54
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_54) ~ counter += 1
  -> region_55
= guarded
~ flags += beta
Guarded stitch 54.
-> region_55
= after_tunnel
Returned from tunnel 54.
-> region_55

=== side_54 ===
Side content 54.
->->

=== ambience_54 ===
+ [Listen 54] -> DONE

=== region_55 ===
Region 55.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_55.hall
+ {counter >= 0} [Guarded path] -> region_55.guarded
+ [Tunnel out] -> side_55 -> region_55.after_tunnel
* [Once only] -> region_55.hall
- (gathered_55) -> region_56
= hall
<- ambience_55
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_55) ~ counter += 1
  -> region_56
= guarded
~ flags += beta
Guarded stitch 55.
-> region_56
= after_tunnel
Returned from tunnel 55.
-> region_56

=== side_55 ===
Side content 55.
->->

=== ambience_55 ===
+ [Listen 55] -> DONE

=== region_56 ===
Region 56.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_56.hall
+ {counter >= 0} [Guarded path] -> region_56.guarded
+ [Tunnel out] -> side_56 -> region_56.after_tunnel
* [Once only] -> region_56.hall
- (gathered_56) -> region_57
= hall
<- ambience_56
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_56) ~ counter += 1
  -> region_57
= guarded
~ flags += beta
Guarded stitch 56.
-> region_57
= after_tunnel
Returned from tunnel 56.
-> region_57

=== side_56 ===
Side content 56.
->->

=== ambience_56 ===
+ [Listen 56] -> DONE

=== region_57 ===
Region 57.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_57.hall
+ {counter >= 0} [Guarded path] -> region_57.guarded
+ [Tunnel out] -> side_57 -> region_57.after_tunnel
* [Once only] -> region_57.hall
- (gathered_57) -> region_58
= hall
<- ambience_57
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_57) ~ counter += 1
  -> region_58
= guarded
~ flags += beta
Guarded stitch 57.
-> region_58
= after_tunnel
Returned from tunnel 57.
-> region_58

=== side_57 ===
Side content 57.
->->

=== ambience_57 ===
+ [Listen 57] -> DONE

=== region_58 ===
Region 58.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_58.hall
+ {counter >= 0} [Guarded path] -> region_58.guarded
+ [Tunnel out] -> side_58 -> region_58.after_tunnel
* [Once only] -> region_58.hall
- (gathered_58) -> region_59
= hall
<- ambience_58
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_58) ~ counter += 1
  -> region_59
= guarded
~ flags += beta
Guarded stitch 58.
-> region_59
= after_tunnel
Returned from tunnel 58.
-> region_59

=== side_58 ===
Side content 58.
->->

=== ambience_58 ===
+ [Listen 58] -> DONE

=== region_59 ===
Region 59.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_59.hall
+ {counter >= 0} [Guarded path] -> region_59.guarded
+ [Tunnel out] -> side_59 -> region_59.after_tunnel
* [Once only] -> region_59.hall
- (gathered_59) -> region_60
= hall
<- ambience_59
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_59) ~ counter += 1
  -> region_60
= guarded
~ flags += beta
Guarded stitch 59.
-> region_60
= after_tunnel
Returned from tunnel 59.
-> region_60

=== side_59 ===
Side content 59.
->->

=== ambience_59 ===
+ [Listen 59] -> DONE

=== region_60 ===
Region 60.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_60.hall
+ {counter >= 0} [Guarded path] -> region_60.guarded
+ [Tunnel out] -> side_60 -> region_60.after_tunnel
* [Once only] -> region_60.hall
- (gathered_60) -> region_61
= hall
<- ambience_60
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_60) ~ counter += 1
  -> region_61
= guarded
~ flags += beta
Guarded stitch 60.
-> region_61
= after_tunnel
Returned from tunnel 60.
-> region_61

=== side_60 ===
Side content 60.
->->

=== ambience_60 ===
+ [Listen 60] -> DONE

=== region_61 ===
Region 61.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_61.hall
+ {counter >= 0} [Guarded path] -> region_61.guarded
+ [Tunnel out] -> side_61 -> region_61.after_tunnel
* [Once only] -> region_61.hall
- (gathered_61) -> region_62
= hall
<- ambience_61
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_61) ~ counter += 1
  -> region_62
= guarded
~ flags += beta
Guarded stitch 61.
-> region_62
= after_tunnel
Returned from tunnel 61.
-> region_62

=== side_61 ===
Side content 61.
->->

=== ambience_61 ===
+ [Listen 61] -> DONE

=== region_62 ===
Region 62.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_62.hall
+ {counter >= 0} [Guarded path] -> region_62.guarded
+ [Tunnel out] -> side_62 -> region_62.after_tunnel
* [Once only] -> region_62.hall
- (gathered_62) -> region_63
= hall
<- ambience_62
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_62) ~ counter += 1
  -> region_63
= guarded
~ flags += beta
Guarded stitch 62.
-> region_63
= after_tunnel
Returned from tunnel 62.
-> region_63

=== side_62 ===
Side content 62.
->->

=== ambience_62 ===
+ [Listen 62] -> DONE

=== region_63 ===
Region 63.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_63.hall
+ {counter >= 0} [Guarded path] -> region_63.guarded
+ [Tunnel out] -> side_63 -> region_63.after_tunnel
* [Once only] -> region_63.hall
- (gathered_63) -> region_64
= hall
<- ambience_63
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_63) ~ counter += 1
  -> region_64
= guarded
~ flags += beta
Guarded stitch 63.
-> region_64
= after_tunnel
Returned from tunnel 63.
-> region_64

=== side_63 ===
Side content 63.
->->

=== ambience_63 ===
+ [Listen 63] -> DONE

=== region_64 ===
Region 64.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_64.hall
+ {counter >= 0} [Guarded path] -> region_64.guarded
+ [Tunnel out] -> side_64 -> region_64.after_tunnel
* [Once only] -> region_64.hall
- (gathered_64) -> region_65
= hall
<- ambience_64
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_64) ~ counter += 1
  -> region_65
= guarded
~ flags += beta
Guarded stitch 64.
-> region_65
= after_tunnel
Returned from tunnel 64.
-> region_65

=== side_64 ===
Side content 64.
->->

=== ambience_64 ===
+ [Listen 64] -> DONE

=== region_65 ===
Region 65.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_65.hall
+ {counter >= 0} [Guarded path] -> region_65.guarded
+ [Tunnel out] -> side_65 -> region_65.after_tunnel
* [Once only] -> region_65.hall
- (gathered_65) -> region_66
= hall
<- ambience_65
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_65) ~ counter += 1
  -> region_66
= guarded
~ flags += beta
Guarded stitch 65.
-> region_66
= after_tunnel
Returned from tunnel 65.
-> region_66

=== side_65 ===
Side content 65.
->->

=== ambience_65 ===
+ [Listen 65] -> DONE

=== region_66 ===
Region 66.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_66.hall
+ {counter >= 0} [Guarded path] -> region_66.guarded
+ [Tunnel out] -> side_66 -> region_66.after_tunnel
* [Once only] -> region_66.hall
- (gathered_66) -> region_67
= hall
<- ambience_66
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_66) ~ counter += 1
  -> region_67
= guarded
~ flags += beta
Guarded stitch 66.
-> region_67
= after_tunnel
Returned from tunnel 66.
-> region_67

=== side_66 ===
Side content 66.
->->

=== ambience_66 ===
+ [Listen 66] -> DONE

=== region_67 ===
Region 67.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_67.hall
+ {counter >= 0} [Guarded path] -> region_67.guarded
+ [Tunnel out] -> side_67 -> region_67.after_tunnel
* [Once only] -> region_67.hall
- (gathered_67) -> region_68
= hall
<- ambience_67
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_67) ~ counter += 1
  -> region_68
= guarded
~ flags += beta
Guarded stitch 67.
-> region_68
= after_tunnel
Returned from tunnel 67.
-> region_68

=== side_67 ===
Side content 67.
->->

=== ambience_67 ===
+ [Listen 67] -> DONE

=== region_68 ===
Region 68.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_68.hall
+ {counter >= 0} [Guarded path] -> region_68.guarded
+ [Tunnel out] -> side_68 -> region_68.after_tunnel
* [Once only] -> region_68.hall
- (gathered_68) -> region_69
= hall
<- ambience_68
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_68) ~ counter += 1
  -> region_69
= guarded
~ flags += beta
Guarded stitch 68.
-> region_69
= after_tunnel
Returned from tunnel 68.
-> region_69

=== side_68 ===
Side content 68.
->->

=== ambience_68 ===
+ [Listen 68] -> DONE

=== region_69 ===
Region 69.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_69.hall
+ {counter >= 0} [Guarded path] -> region_69.guarded
+ [Tunnel out] -> side_69 -> region_69.after_tunnel
* [Once only] -> region_69.hall
- (gathered_69) -> region_70
= hall
<- ambience_69
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_69) ~ counter += 1
  -> region_70
= guarded
~ flags += beta
Guarded stitch 69.
-> region_70
= after_tunnel
Returned from tunnel 69.
-> region_70

=== side_69 ===
Side content 69.
->->

=== ambience_69 ===
+ [Listen 69] -> DONE

=== region_70 ===
Region 70.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_70.hall
+ {counter >= 0} [Guarded path] -> region_70.guarded
+ [Tunnel out] -> side_70 -> region_70.after_tunnel
* [Once only] -> region_70.hall
- (gathered_70) -> region_71
= hall
<- ambience_70
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_70) ~ counter += 1
  -> region_71
= guarded
~ flags += beta
Guarded stitch 70.
-> region_71
= after_tunnel
Returned from tunnel 70.
-> region_71

=== side_70 ===
Side content 70.
->->

=== ambience_70 ===
+ [Listen 70] -> DONE

=== region_71 ===
Region 71.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_71.hall
+ {counter >= 0} [Guarded path] -> region_71.guarded
+ [Tunnel out] -> side_71 -> region_71.after_tunnel
* [Once only] -> region_71.hall
- (gathered_71) -> region_72
= hall
<- ambience_71
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_71) ~ counter += 1
  -> region_72
= guarded
~ flags += beta
Guarded stitch 71.
-> region_72
= after_tunnel
Returned from tunnel 71.
-> region_72

=== side_71 ===
Side content 71.
->->

=== ambience_71 ===
+ [Listen 71] -> DONE

=== region_72 ===
Region 72.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_72.hall
+ {counter >= 0} [Guarded path] -> region_72.guarded
+ [Tunnel out] -> side_72 -> region_72.after_tunnel
* [Once only] -> region_72.hall
- (gathered_72) -> region_73
= hall
<- ambience_72
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_72) ~ counter += 1
  -> region_73
= guarded
~ flags += beta
Guarded stitch 72.
-> region_73
= after_tunnel
Returned from tunnel 72.
-> region_73

=== side_72 ===
Side content 72.
->->

=== ambience_72 ===
+ [Listen 72] -> DONE

=== region_73 ===
Region 73.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_73.hall
+ {counter >= 0} [Guarded path] -> region_73.guarded
+ [Tunnel out] -> side_73 -> region_73.after_tunnel
* [Once only] -> region_73.hall
- (gathered_73) -> region_74
= hall
<- ambience_73
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_73) ~ counter += 1
  -> region_74
= guarded
~ flags += beta
Guarded stitch 73.
-> region_74
= after_tunnel
Returned from tunnel 73.
-> region_74

=== side_73 ===
Side content 73.
->->

=== ambience_73 ===
+ [Listen 73] -> DONE

=== region_74 ===
Region 74.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_74.hall
+ {counter >= 0} [Guarded path] -> region_74.guarded
+ [Tunnel out] -> side_74 -> region_74.after_tunnel
* [Once only] -> region_74.hall
- (gathered_74) -> region_75
= hall
<- ambience_74
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_74) ~ counter += 1
  -> region_75
= guarded
~ flags += beta
Guarded stitch 74.
-> region_75
= after_tunnel
Returned from tunnel 74.
-> region_75

=== side_74 ===
Side content 74.
->->

=== ambience_74 ===
+ [Listen 74] -> DONE

=== region_75 ===
Region 75.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_75.hall
+ {counter >= 0} [Guarded path] -> region_75.guarded
+ [Tunnel out] -> side_75 -> region_75.after_tunnel
* [Once only] -> region_75.hall
- (gathered_75) -> region_76
= hall
<- ambience_75
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_75) ~ counter += 1
  -> region_76
= guarded
~ flags += beta
Guarded stitch 75.
-> region_76
= after_tunnel
Returned from tunnel 75.
-> region_76

=== side_75 ===
Side content 75.
->->

=== ambience_75 ===
+ [Listen 75] -> DONE

=== region_76 ===
Region 76.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_76.hall
+ {counter >= 0} [Guarded path] -> region_76.guarded
+ [Tunnel out] -> side_76 -> region_76.after_tunnel
* [Once only] -> region_76.hall
- (gathered_76) -> region_77
= hall
<- ambience_76
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_76) ~ counter += 1
  -> region_77
= guarded
~ flags += beta
Guarded stitch 76.
-> region_77
= after_tunnel
Returned from tunnel 76.
-> region_77

=== side_76 ===
Side content 76.
->->

=== ambience_76 ===
+ [Listen 76] -> DONE

=== region_77 ===
Region 77.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_77.hall
+ {counter >= 0} [Guarded path] -> region_77.guarded
+ [Tunnel out] -> side_77 -> region_77.after_tunnel
* [Once only] -> region_77.hall
- (gathered_77) -> region_78
= hall
<- ambience_77
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_77) ~ counter += 1
  -> region_78
= guarded
~ flags += beta
Guarded stitch 77.
-> region_78
= after_tunnel
Returned from tunnel 77.
-> region_78

=== side_77 ===
Side content 77.
->->

=== ambience_77 ===
+ [Listen 77] -> DONE

=== region_78 ===
Region 78.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_78.hall
+ {counter >= 0} [Guarded path] -> region_78.guarded
+ [Tunnel out] -> side_78 -> region_78.after_tunnel
* [Once only] -> region_78.hall
- (gathered_78) -> region_79
= hall
<- ambience_78
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_78) ~ counter += 1
  -> region_79
= guarded
~ flags += beta
Guarded stitch 78.
-> region_79
= after_tunnel
Returned from tunnel 78.
-> region_79

=== side_78 ===
Side content 78.
->->

=== ambience_78 ===
+ [Listen 78] -> DONE

=== region_79 ===
Region 79.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_79.hall
+ {counter >= 0} [Guarded path] -> region_79.guarded
+ [Tunnel out] -> side_79 -> region_79.after_tunnel
* [Once only] -> region_79.hall
- (gathered_79) -> region_80
= hall
<- ambience_79
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_79) ~ counter += 1
  -> region_80
= guarded
~ flags += beta
Guarded stitch 79.
-> region_80
= after_tunnel
Returned from tunnel 79.
-> region_80

=== side_79 ===
Side content 79.
->->

=== ambience_79 ===
+ [Listen 79] -> DONE

=== region_80 ===
Region 80.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_80.hall
+ {counter >= 0} [Guarded path] -> region_80.guarded
+ [Tunnel out] -> side_80 -> region_80.after_tunnel
* [Once only] -> region_80.hall
- (gathered_80) -> region_81
= hall
<- ambience_80
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_80) ~ counter += 1
  -> region_81
= guarded
~ flags += beta
Guarded stitch 80.
-> region_81
= after_tunnel
Returned from tunnel 80.
-> region_81

=== side_80 ===
Side content 80.
->->

=== ambience_80 ===
+ [Listen 80] -> DONE

=== region_81 ===
Region 81.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_81.hall
+ {counter >= 0} [Guarded path] -> region_81.guarded
+ [Tunnel out] -> side_81 -> region_81.after_tunnel
* [Once only] -> region_81.hall
- (gathered_81) -> region_82
= hall
<- ambience_81
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_81) ~ counter += 1
  -> region_82
= guarded
~ flags += beta
Guarded stitch 81.
-> region_82
= after_tunnel
Returned from tunnel 81.
-> region_82

=== side_81 ===
Side content 81.
->->

=== ambience_81 ===
+ [Listen 81] -> DONE

=== region_82 ===
Region 82.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_82.hall
+ {counter >= 0} [Guarded path] -> region_82.guarded
+ [Tunnel out] -> side_82 -> region_82.after_tunnel
* [Once only] -> region_82.hall
- (gathered_82) -> region_83
= hall
<- ambience_82
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_82) ~ counter += 1
  -> region_83
= guarded
~ flags += beta
Guarded stitch 82.
-> region_83
= after_tunnel
Returned from tunnel 82.
-> region_83

=== side_82 ===
Side content 82.
->->

=== ambience_82 ===
+ [Listen 82] -> DONE

=== region_83 ===
Region 83.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_83.hall
+ {counter >= 0} [Guarded path] -> region_83.guarded
+ [Tunnel out] -> side_83 -> region_83.after_tunnel
* [Once only] -> region_83.hall
- (gathered_83) -> region_84
= hall
<- ambience_83
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_83) ~ counter += 1
  -> region_84
= guarded
~ flags += beta
Guarded stitch 83.
-> region_84
= after_tunnel
Returned from tunnel 83.
-> region_84

=== side_83 ===
Side content 83.
->->

=== ambience_83 ===
+ [Listen 83] -> DONE

=== region_84 ===
Region 84.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_84.hall
+ {counter >= 0} [Guarded path] -> region_84.guarded
+ [Tunnel out] -> side_84 -> region_84.after_tunnel
* [Once only] -> region_84.hall
- (gathered_84) -> region_85
= hall
<- ambience_84
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_84) ~ counter += 1
  -> region_85
= guarded
~ flags += beta
Guarded stitch 84.
-> region_85
= after_tunnel
Returned from tunnel 84.
-> region_85

=== side_84 ===
Side content 84.
->->

=== ambience_84 ===
+ [Listen 84] -> DONE

=== region_85 ===
Region 85.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_85.hall
+ {counter >= 0} [Guarded path] -> region_85.guarded
+ [Tunnel out] -> side_85 -> region_85.after_tunnel
* [Once only] -> region_85.hall
- (gathered_85) -> region_86
= hall
<- ambience_85
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_85) ~ counter += 1
  -> region_86
= guarded
~ flags += beta
Guarded stitch 85.
-> region_86
= after_tunnel
Returned from tunnel 85.
-> region_86

=== side_85 ===
Side content 85.
->->

=== ambience_85 ===
+ [Listen 85] -> DONE

=== region_86 ===
Region 86.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_86.hall
+ {counter >= 0} [Guarded path] -> region_86.guarded
+ [Tunnel out] -> side_86 -> region_86.after_tunnel
* [Once only] -> region_86.hall
- (gathered_86) -> region_87
= hall
<- ambience_86
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_86) ~ counter += 1
  -> region_87
= guarded
~ flags += beta
Guarded stitch 86.
-> region_87
= after_tunnel
Returned from tunnel 86.
-> region_87

=== side_86 ===
Side content 86.
->->

=== ambience_86 ===
+ [Listen 86] -> DONE

=== region_87 ===
Region 87.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_87.hall
+ {counter >= 0} [Guarded path] -> region_87.guarded
+ [Tunnel out] -> side_87 -> region_87.after_tunnel
* [Once only] -> region_87.hall
- (gathered_87) -> region_88
= hall
<- ambience_87
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_87) ~ counter += 1
  -> region_88
= guarded
~ flags += beta
Guarded stitch 87.
-> region_88
= after_tunnel
Returned from tunnel 87.
-> region_88

=== side_87 ===
Side content 87.
->->

=== ambience_87 ===
+ [Listen 87] -> DONE

=== region_88 ===
Region 88.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_88.hall
+ {counter >= 0} [Guarded path] -> region_88.guarded
+ [Tunnel out] -> side_88 -> region_88.after_tunnel
* [Once only] -> region_88.hall
- (gathered_88) -> region_89
= hall
<- ambience_88
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_88) ~ counter += 1
  -> region_89
= guarded
~ flags += beta
Guarded stitch 88.
-> region_89
= after_tunnel
Returned from tunnel 88.
-> region_89

=== side_88 ===
Side content 88.
->->

=== ambience_88 ===
+ [Listen 88] -> DONE

=== region_89 ===
Region 89.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_89.hall
+ {counter >= 0} [Guarded path] -> region_89.guarded
+ [Tunnel out] -> side_89 -> region_89.after_tunnel
* [Once only] -> region_89.hall
- (gathered_89) -> region_90
= hall
<- ambience_89
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_89) ~ counter += 1
  -> region_90
= guarded
~ flags += beta
Guarded stitch 89.
-> region_90
= after_tunnel
Returned from tunnel 89.
-> region_90

=== side_89 ===
Side content 89.
->->

=== ambience_89 ===
+ [Listen 89] -> DONE

=== region_90 ===
Region 90.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_90.hall
+ {counter >= 0} [Guarded path] -> region_90.guarded
+ [Tunnel out] -> side_90 -> region_90.after_tunnel
* [Once only] -> region_90.hall
- (gathered_90) -> region_91
= hall
<- ambience_90
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_90) ~ counter += 1
  -> region_91
= guarded
~ flags += beta
Guarded stitch 90.
-> region_91
= after_tunnel
Returned from tunnel 90.
-> region_91

=== side_90 ===
Side content 90.
->->

=== ambience_90 ===
+ [Listen 90] -> DONE

=== region_91 ===
Region 91.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_91.hall
+ {counter >= 0} [Guarded path] -> region_91.guarded
+ [Tunnel out] -> side_91 -> region_91.after_tunnel
* [Once only] -> region_91.hall
- (gathered_91) -> region_92
= hall
<- ambience_91
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_91) ~ counter += 1
  -> region_92
= guarded
~ flags += beta
Guarded stitch 91.
-> region_92
= after_tunnel
Returned from tunnel 91.
-> region_92

=== side_91 ===
Side content 91.
->->

=== ambience_91 ===
+ [Listen 91] -> DONE

=== region_92 ===
Region 92.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_92.hall
+ {counter >= 0} [Guarded path] -> region_92.guarded
+ [Tunnel out] -> side_92 -> region_92.after_tunnel
* [Once only] -> region_92.hall
- (gathered_92) -> region_93
= hall
<- ambience_92
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_92) ~ counter += 1
  -> region_93
= guarded
~ flags += beta
Guarded stitch 92.
-> region_93
= after_tunnel
Returned from tunnel 92.
-> region_93

=== side_92 ===
Side content 92.
->->

=== ambience_92 ===
+ [Listen 92] -> DONE

=== region_93 ===
Region 93.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_93.hall
+ {counter >= 0} [Guarded path] -> region_93.guarded
+ [Tunnel out] -> side_93 -> region_93.after_tunnel
* [Once only] -> region_93.hall
- (gathered_93) -> region_94
= hall
<- ambience_93
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_93) ~ counter += 1
  -> region_94
= guarded
~ flags += beta
Guarded stitch 93.
-> region_94
= after_tunnel
Returned from tunnel 93.
-> region_94

=== side_93 ===
Side content 93.
->->

=== ambience_93 ===
+ [Listen 93] -> DONE

=== region_94 ===
Region 94.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_94.hall
+ {counter >= 0} [Guarded path] -> region_94.guarded
+ [Tunnel out] -> side_94 -> region_94.after_tunnel
* [Once only] -> region_94.hall
- (gathered_94) -> region_95
= hall
<- ambience_94
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_94) ~ counter += 1
  -> region_95
= guarded
~ flags += beta
Guarded stitch 94.
-> region_95
= after_tunnel
Returned from tunnel 94.
-> region_95

=== side_94 ===
Side content 94.
->->

=== ambience_94 ===
+ [Listen 94] -> DONE

=== region_95 ===
Region 95.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_95.hall
+ {counter >= 0} [Guarded path] -> region_95.guarded
+ [Tunnel out] -> side_95 -> region_95.after_tunnel
* [Once only] -> region_95.hall
- (gathered_95) -> region_96
= hall
<- ambience_95
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_95) ~ counter += 1
  -> region_96
= guarded
~ flags += beta
Guarded stitch 95.
-> region_96
= after_tunnel
Returned from tunnel 95.
-> region_96

=== side_95 ===
Side content 95.
->->

=== ambience_95 ===
+ [Listen 95] -> DONE

=== region_96 ===
Region 96.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_96.hall
+ {counter >= 0} [Guarded path] -> region_96.guarded
+ [Tunnel out] -> side_96 -> region_96.after_tunnel
* [Once only] -> region_96.hall
- (gathered_96) -> region_97
= hall
<- ambience_96
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_96) ~ counter += 1
  -> region_97
= guarded
~ flags += beta
Guarded stitch 96.
-> region_97
= after_tunnel
Returned from tunnel 96.
-> region_97

=== side_96 ===
Side content 96.
->->

=== ambience_96 ===
+ [Listen 96] -> DONE

=== region_97 ===
Region 97.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_97.hall
+ {counter >= 0} [Guarded path] -> region_97.guarded
+ [Tunnel out] -> side_97 -> region_97.after_tunnel
* [Once only] -> region_97.hall
- (gathered_97) -> region_98
= hall
<- ambience_97
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_97) ~ counter += 1
  -> region_98
= guarded
~ flags += beta
Guarded stitch 97.
-> region_98
= after_tunnel
Returned from tunnel 97.
-> region_98

=== side_97 ===
Side content 97.
->->

=== ambience_97 ===
+ [Listen 97] -> DONE

=== region_98 ===
Region 98.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_98.hall
+ {counter >= 0} [Guarded path] -> region_98.guarded
+ [Tunnel out] -> side_98 -> region_98.after_tunnel
* [Once only] -> region_98.hall
- (gathered_98) -> region_99
= hall
<- ambience_98
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_98) ~ counter += 1
  -> region_99
= guarded
~ flags += beta
Guarded stitch 98.
-> region_99
= after_tunnel
Returned from tunnel 98.
-> region_99

=== side_98 ===
Side content 98.
->->

=== ambience_98 ===
+ [Listen 98] -> DONE

=== region_99 ===
Region 99.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_99.hall
+ {counter >= 0} [Guarded path] -> region_99.guarded
+ [Tunnel out] -> side_99 -> region_99.after_tunnel
* [Once only] -> region_99.hall
- (gathered_99) -> region_100
= hall
<- ambience_99
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_99) ~ counter += 1
  -> region_100
= guarded
~ flags += beta
Guarded stitch 99.
-> region_100
= after_tunnel
Returned from tunnel 99.
-> region_100

=== side_99 ===
Side content 99.
->->

=== ambience_99 ===
+ [Listen 99] -> DONE

=== region_100 ===
Region 100.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_100.hall
+ {counter >= 0} [Guarded path] -> region_100.guarded
+ [Tunnel out] -> side_100 -> region_100.after_tunnel
* [Once only] -> region_100.hall
- (gathered_100) -> region_101
= hall
<- ambience_100
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_100) ~ counter += 1
  -> region_101
= guarded
~ flags += beta
Guarded stitch 100.
-> region_101
= after_tunnel
Returned from tunnel 100.
-> region_101

=== side_100 ===
Side content 100.
->->

=== ambience_100 ===
+ [Listen 100] -> DONE

=== region_101 ===
Region 101.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_101.hall
+ {counter >= 0} [Guarded path] -> region_101.guarded
+ [Tunnel out] -> side_101 -> region_101.after_tunnel
* [Once only] -> region_101.hall
- (gathered_101) -> region_102
= hall
<- ambience_101
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_101) ~ counter += 1
  -> region_102
= guarded
~ flags += beta
Guarded stitch 101.
-> region_102
= after_tunnel
Returned from tunnel 101.
-> region_102

=== side_101 ===
Side content 101.
->->

=== ambience_101 ===
+ [Listen 101] -> DONE

=== region_102 ===
Region 102.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_102.hall
+ {counter >= 0} [Guarded path] -> region_102.guarded
+ [Tunnel out] -> side_102 -> region_102.after_tunnel
* [Once only] -> region_102.hall
- (gathered_102) -> region_103
= hall
<- ambience_102
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_102) ~ counter += 1
  -> region_103
= guarded
~ flags += beta
Guarded stitch 102.
-> region_103
= after_tunnel
Returned from tunnel 102.
-> region_103

=== side_102 ===
Side content 102.
->->

=== ambience_102 ===
+ [Listen 102] -> DONE

=== region_103 ===
Region 103.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_103.hall
+ {counter >= 0} [Guarded path] -> region_103.guarded
+ [Tunnel out] -> side_103 -> region_103.after_tunnel
* [Once only] -> region_103.hall
- (gathered_103) -> region_104
= hall
<- ambience_103
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_103) ~ counter += 1
  -> region_104
= guarded
~ flags += beta
Guarded stitch 103.
-> region_104
= after_tunnel
Returned from tunnel 103.
-> region_104

=== side_103 ===
Side content 103.
->->

=== ambience_103 ===
+ [Listen 103] -> DONE

=== region_104 ===
Region 104.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_104.hall
+ {counter >= 0} [Guarded path] -> region_104.guarded
+ [Tunnel out] -> side_104 -> region_104.after_tunnel
* [Once only] -> region_104.hall
- (gathered_104) -> region_105
= hall
<- ambience_104
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_104) ~ counter += 1
  -> region_105
= guarded
~ flags += beta
Guarded stitch 104.
-> region_105
= after_tunnel
Returned from tunnel 104.
-> region_105

=== side_104 ===
Side content 104.
->->

=== ambience_104 ===
+ [Listen 104] -> DONE

=== region_105 ===
Region 105.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_105.hall
+ {counter >= 0} [Guarded path] -> region_105.guarded
+ [Tunnel out] -> side_105 -> region_105.after_tunnel
* [Once only] -> region_105.hall
- (gathered_105) -> region_106
= hall
<- ambience_105
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_105) ~ counter += 1
  -> region_106
= guarded
~ flags += beta
Guarded stitch 105.
-> region_106
= after_tunnel
Returned from tunnel 105.
-> region_106

=== side_105 ===
Side content 105.
->->

=== ambience_105 ===
+ [Listen 105] -> DONE

=== region_106 ===
Region 106.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_106.hall
+ {counter >= 0} [Guarded path] -> region_106.guarded
+ [Tunnel out] -> side_106 -> region_106.after_tunnel
* [Once only] -> region_106.hall
- (gathered_106) -> region_107
= hall
<- ambience_106
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_106) ~ counter += 1
  -> region_107
= guarded
~ flags += beta
Guarded stitch 106.
-> region_107
= after_tunnel
Returned from tunnel 106.
-> region_107

=== side_106 ===
Side content 106.
->->

=== ambience_106 ===
+ [Listen 106] -> DONE

=== region_107 ===
Region 107.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_107.hall
+ {counter >= 0} [Guarded path] -> region_107.guarded
+ [Tunnel out] -> side_107 -> region_107.after_tunnel
* [Once only] -> region_107.hall
- (gathered_107) -> region_108
= hall
<- ambience_107
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_107) ~ counter += 1
  -> region_108
= guarded
~ flags += beta
Guarded stitch 107.
-> region_108
= after_tunnel
Returned from tunnel 107.
-> region_108

=== side_107 ===
Side content 107.
->->

=== ambience_107 ===
+ [Listen 107] -> DONE

=== region_108 ===
Region 108.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_108.hall
+ {counter >= 0} [Guarded path] -> region_108.guarded
+ [Tunnel out] -> side_108 -> region_108.after_tunnel
* [Once only] -> region_108.hall
- (gathered_108) -> region_109
= hall
<- ambience_108
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_108) ~ counter += 1
  -> region_109
= guarded
~ flags += beta
Guarded stitch 108.
-> region_109
= after_tunnel
Returned from tunnel 108.
-> region_109

=== side_108 ===
Side content 108.
->->

=== ambience_108 ===
+ [Listen 108] -> DONE

=== region_109 ===
Region 109.
{~A|B|C} {&x|y} {!once|twice}
{ flags ? alpha: Alpha here. | No alpha. }
+ [Enter hall] -> region_109.hall
+ {counter >= 0} [Guarded path] -> region_109.guarded
+ [Tunnel out] -> side_109 -> region_109.after_tunnel
* [Once only] -> region_109.hall
- (gathered_109) -> finale
= hall
<- ambience_109
The hall.
  * [Left] 
    Going left.
    ** [Deeper left] Deep.
    ** [Back] Back.
    -- (inner_l) Rejoined.
  * [Right]
    Going right.
    ** [Deeper right] Deep.
    -- (inner_r) Rejoined.
  - (outer_109) ~ counter += 1
  -> finale
= guarded
~ flags += beta
Guarded stitch 109.
-> finale
= after_tunnel
Returned from tunnel 109.
-> finale

=== side_109 ===
Side content 109.
->->

=== ambience_109 ===
+ [Listen 109] -> DONE

=== finale ===
Done.
-> END
