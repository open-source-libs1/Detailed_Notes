
total_amounts = {}

for item in transaction_list:
    sender = item["sender"]
    amount = item["amount"]

    if sender not in total_amounts:
        total_amounts[sender] = 0

    total_amounts[sender] += amount

max_sender = None
max_amount = 0

for sender in total_amounts:
    if total_amounts[sender] > max_amount:
        max_amount = total_amounts[sender]
        max_sender = sender

print(f"Max sender is {max_sender} and sent amount of {max_amount}")

####################

words = ["a", "b", "a", "c", "b", "a"]

counts = {}
for w in words:
    if w not in counts:
        counts[w] = 0
    counts[w] += 1

max_word = None
max_count = 0
for w in counts:
    if counts[w] > max_count:
        max_count = counts[w]
        max_word = w

print(max_word, max_count)



##############################


s = "swiss"

counts = {}
for ch in s:
    if ch not in counts:
        counts[ch] = 0
    counts[ch] += 1

answer = None
for ch in s:
    if counts[ch] == 1:
        answer = ch
        break

print(answer)



##############################


nums = [10, 5, 20, 8, 20]

largest = None
second = None

for n in nums:
    if largest is None or n > largest:
        second = largest
        largest = n
    elif n != largest and (second is None or n > second):
        second = n

print("Second largest:", second)


########################

nums = [2, 7, 11, 15]
target = 9

seen = {}
found = False

for n in nums:
    need = target - n
    if need in seen:
        found = True
        break
    seen[n] = True

print(found)



#########################


s = "{[()]}"

stack = []
pairs = {")": "(", "]": "[", "}": "{"}
valid = True

for ch in s:
    if ch in "([{":
        stack.append(ch)
    else:
        if len(stack) == 0 or stack[-1] != pairs[ch]:
            valid = False
            break
        stack.pop()

if len(stack) != 0:
    valid = False

print(valid)
