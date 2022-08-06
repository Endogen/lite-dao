Proposals = Hash(default_value = None)
ProposalCount = Variable
Ballots = Hash(default_value = False)
BallotCount = Hash(default_value = 0)
ProposalCount = Variable()
ProcessedBallots = Hash(default_value = 0)
VerifiedBallots = Hash(default_value = 0)
LPWeight = Hash(default_value = 0)
FinalCount = Hash(default_value = 0)
metadata = Hash(default_value = None)

I = importlib

@construct
def seed():
    metadata['operator'] = ctx.caller
    metadata['fee_currency'] = 'con_rswp_lst001'
    metadata['fee_amount'] = 27272 # $30 3/7/22
    metadata['token_contract'] = 'con_rswp_lst001'
    metadata['v_token_contracts'] = ['con_staking_rswp_rswp_interop_v2']
    metadata['lp_v_token_contracts'] = ['con_liq_mining_rswp_rswp']
    metadata['dex_contract'] = 'con_rocketswap_official_v1_1'
    metadata['min_description_length'] = 10
    metadata['min_title_length'] = 10

    ProposalCount.set(0)


@export 
def create_proposal(title:str, description: str, date_decision: datetime.datetime, choices: list):
    assert len(title) > metadata['min_title_length'], 'Title must be more than 10 characters long.'
    assert len(description) > metadata['min_description_length'], 'Description length must be more than 100 characters long.'
    assert date_decision > now,    'the decision date must take place in the future.'
    assert len(choices) > 1, 'you must specify at least 2 choices.'

    for choice in choices:
        assert len(choice) > 0, 'choice cannot be an empty string.'

    ProposalCount.set(ProposalCount.get() + 1)
    Proposals[ProposalCount.get()] = {
        "title":title,
        "description": description,
        "date_decision": date_decision,
        "choices": choices,
        "state": "open"
    }
    deduct_fee()


def deduct_fee():
    token_contract = I.import_module(metadata['fee_currency'])
    token_contract.transfer_from(amount=metadata['fee_amount'], to=metadata['operator'], main_account=ctx.signer)
    

@export 
def count_ballots(proposal_idx: int, batch_size: int = 100):
    '''checks'''
    assert now > Proposals[proposal_idx]["date_decision"], 'It is not possible to count the ballots for this proposal yet'
    assert Proposals[proposal_idx]["state"] is not "concluded", 'The ballots for this proposal have already been counted'
    assert Ballots[proposal_idx, "counted"] is not True, 'this ballot has been counted.'
    '''check if this proposal has a stored lp token weight, if no, calculate how much the LP weight is worth'''
    token_contract_name = metadata['token_contract']
    if LPWeight[proposal_idx,token_contract] is 0:
         set_lp_token_value(token_contract_name=token_contract_name)
    
    start_idx = ProcessedBallots[proposal_idx]
    counted_ballots = ProcessedBallots[proposal_idx]

    current_ballot_idx = 0

    '''count the ballots'''
    for i in range(0, batch_size):        
        current_ballot_idx = start_idx + i
        
        voter_vk = Ballots[proposal_idx,"forwards_index",ballot_idx,"user_vk"]

        ProcessedBallots[proposal_idx, current_ballot_idx, "choice"] = Ballots[proposal_idx,"forwards_index", current_ballot_idx, "choice"]
        ProcessedBallots[proposal_idx, current_ballot_idx, "user_vk"] = voter_vk
        ProcessedBallots[proposal_idx, current_ballot_idx, "weight"] = get_vk_weight(vk=voter_vk)

        if current_ballot_idx == BallotCount[proposal_idx]:
            # Mark ballot count as ready for verification.

            Ballots[proposal_idx, "counted"] = True
            return

    ProcessedBallots[proposal_idx] = current_ballot_idx


@export 
def verify_ballots(proposal_idx: int, batch_size: int = 100):
    '''checks'''
    assert Ballots[proposal_idx, "counted"] is True, 'ballots must be counted before verifying them'
    assert Ballots[proposal_idx, "verified"] is not True, 'the ballots for this proposal have already been verified'
    assert Proposals[proposal_idx]["state"] is not "concluded", 'this proposal has been concluded'

    start_idx = VerifiedBallots[proposal_idx]
    current_ballot_idx = 0

    for i in range(0, batch_size):
        current_ballot_idx = start_idx + i

        user_vk = Ballots[proposal_idx, current_ballot_idx, "user_vk"]
        choice = Ballots[proposal_idx, current_ballot_idx, "choice"]
        processed_weight = Ballots[proposal_idx, current_ballot_idx, "weight"]

        current_weight = get_vk_weight(vk=voter_vk)

        if current_weight >= processed_weight - (processed_weight * 0.05):
            VerifiedBallots[proposal_idx, choice] += current_weight
        
        if current_ballot_idx == BallotCount[proposal_idx]:

            choices_len = len(Proposals[proposal_idx]["results"])
            Ballots[proposal_idx, "verified"] = True
            Proposals[proposal_idx]["state"] = "concluded"
            Proposals[proposal_idx]["results"] = {}

            for c in range(0, choices_len):
                Proposals[proposal_idx]["results"][c] = VerifiedBallots[proposal_idx, c]
                
            Proposals[proposal_idx] = Proposals[proposal_idx]

            return

    VerifiedBallots[proposal_idx] = current_ballot_idx
    

@export 
def cast_ballot(proposal_idx: int, choice_idx: int):    
    ballot_idx = BallotCount[proposal_idx]
    
    '''checks'''
    assert Proposals[proposal_idx] is not False
    assert choice_idx < len(Proposals[proposal_idx]["choices"]), 'you must select a valid choice.'
    assert now < Proposals[proposal_idx]["date_decision"], 'It is too late to cast a ballot for this proposal.'
    assert Ballots[proposal_idx,"backwards_index", ctx.signer] is False, 'you have already cast a ballot !'

    '''record ballot'''
    Ballots[proposal_idx,"forwards_index",ballot_idx,"choice"] = choice_idx
    Ballots[proposal_idx,"forwards_index",ballot_idx,"user_vk"] = ctx.signer
    Ballots[proposal_idx,"backwards_index", ctx.signer] = ballot_idx
    
    BallotCount[proposal_idx] += 1


def get_vk_weight(vk:str, proposal_idx: str):
    '''
    Get the rswp value of any tokens, vtokens and LP tokens for rswp pairs (staked or not). 
    '''
    token_contract_name = metadata['token_contract']
    user_token_total = 0

    user_token_total += get_token_value(vk=vk, token_contract_name=token_contract_name)
    user_token_total += get_staked_token_value(vk=vk, token_contract_name=token_contract_name)
    user_token_total += get_staked_lp_value(vk=vk, proposal_idx=proposal_idx)
    user_token_total += get_lp_value(vk=vk, proposal_idx=proposal_idx)
    user_token_total += get_rocketfuel_value(vk=vk, token_contract_name=token_contract_name)

    return user_token_total


def get_token_value(vk:str, token_contract_name:str):
    ForeignHash(foreign_contract=token_contract_name, foreign_name='balances')
    token_balance = token_contract["balances",vk] or 0

    return token_balance
    

def get_rocketfuel_value(vk:str, token_contract_name: str):
    '''
    get value of RSWP staked in rocket fuel
    '''
    dex_contract_name = metadata['dex_contract']
    dex_staked_amount = ForeignHash(foreign_contract=dex_contract_name, foreign_name='staked_amount')
    user_rocketfuel = dex_staked_amount[vk, token_contract_name] or 0
    
    return user_rocketfuel


def get_lp_value(vk:str, token_contract_name: str):
    '''
    get lp value from the dex contract
    '''
    dex_contract_name = metadata['dex_contract']
    dex_lp_points = ForeignHash(foreign_contract=dex_contract_name, foreign_name='lp_points')
    user_lp = dex_lp_points[token_contract_name, vk] or 0

    return user_lp * LPWeight[proposal_idx,token_contract]


def get_staked_lp_value(vk: str, proposal_idx: int, token_contract_name:str):
    lp_count = 0
    staking_contract_names = LPmetadata['v_token_contracts']
    lp_token_value = LPWeight[proposal_idx,token_contract_name]

    for contract in staking_contract_names:
        balances = ForeignHash(foreign_contract=contract, foreign_name='balances')
        vk_balance = balances[vk] or 0
        lp_count += vk_balance

    return lp_count * LPWeight[proposal_idx,token_contract]


def get_staked_token_value(vk: str):
    '''iterate through v token contracts and get user balance.'''
    count = 0
    staking_contract_names = metadata['v_token_contracts']

    for contract in staking_contract_names:
        balances = ForeignHash(foreign_contract=contract, foreign_name='balances')
        vk_balance = balances[vk] or 0

    return count


def set_lp_token_value(token_contract_name: str):
    '''
    import the dex contract, get the reserves value for the TAU-RSWP pair, take the RSWP value of the LP and multiply it by 2
    '''
    dex_contract_name = metadata['dex_contract']
    dex_reserves = ForeignHash(foreign_contract=dex_contract_name, foreign_name='reserves')
    dex_lp_points = ForeignHash(foreign_contract=dex_contract_name, foreign_name='lp_points')

    reserves = dex_reserves[token_contract_name]
    total_lp = dex_lp_points[token_contract_name]
    token_per_lp = reserves[1] / total_lp

    LPWeight[proposal_idx,token_contract] = token_per_lp * 2


def assert_operator():
    assert ctx.caller == metadata['operator'], "You are not the listed operator for this contract."


@export
def change_meta(key: str, value: Any):
    assert ctx.caller == metadata['operator'], 'Only operator can set metadata!'
    metadata[key] = value