import pytest
import math
import itertools
from pathlib import Path
from thermodynamic_objects import *
from RefrigerationSimulator import RefrigerationSimulator

'''
Test input validation
'''
@pytest.fixture
def mock_excel(monkeypatch):
    # mock Compressors and Condensers data
    df_comp = pd.DataFrame({'Compressor': ['Compressor_A', 'Compressor_B'], 'Refrigerant': ['R134a', 'R404a']})
    df_cond = pd.DataFrame({'Model': ['Condenser_A', 'Condenser_B'], 'Fan': ['Fan_A', 'Fan_B'], 'Refrigerant': ['R404a', 'R134a']})

    def mock_read_excel(file, sheet_name):
        if file == "components_data.xlsx":
            if sheet_name == "Compressors":
                return df_comp
            elif sheet_name == "Condensers":
                return df_cond
        else:
            raise FileNotFoundError
    monkeypatch.setattr(pd, "read_excel", mock_read_excel)

    # mock refrigerants
    monkeypatch.setattr("RefrigerationSimulator.get_global_param_string", lambda x: ["R404A", "R410A", "R134a"])

@pytest.mark.parametrize("data_source, ref, mode, compressor_model, condenser_model, fan_model, should_raise, exc_type", [
        ("components_data.xlsx", "R404A", ["inverter", "MT"], "Compressor_B", "Condenser_A", "Fan_A", False, None),
        ("dummy.xlsx", "R404A", ["fixed", "MT"], "Compressor_B", "Condenser_A", "Fan_A", True, FileNotFoundError),
        ("components_data.xlsx", "invalid", ["inverter", "LT"], "Compressor_B", "Condenser_A", "Fan_A", True, ValueError),
        ("components_data.xlsx", "R404A", ["invalid", "MT"], "Compressor_B", "Condenser_A", "Fan_A", True, ValueError),
        ("components_data.xlsx", "R404A", ["inverter", "invalid"], "Compressor_B", "Condenser_A", "Fan_A", True, ValueError),
        ("components_data.xlsx", "R404A", ["fixed", "LT"], "invalid", "Condenser_A", "Fan_A", True, ValueError),
        ("components_data.xlsx", "R404A", ["inverter", "LT"], "Compressor_B", "invalid", "Fan_A", True, ValueError),
        ("components_data.xlsx", "R404A", ["fixed", "MT"], "Compressor_B", "Condenser_A", "invalid", True, ValueError),
        ("components_data.xlsx", "R134a", ["inverter", "MT"], "Compressor_B", "Condenser_B", "Fan_B", True, ValueError),
        ("components_data.xlsx", "R134a", ["inverter", "MT"], "Compressor_A", "Condenser_A", "Fan_A", True, ValueError),
    ])

def test_input_validation_for_non_existing(mock_excel, data_source, ref, mode, compressor_model, condenser_model, fan_model, should_raise, exc_type):
    sim = RefrigerationSimulator(
        run_simulation=False, run_SEPR_calculation=False, mode_use_declared=False, show_report=False,
        data_source=data_source, compressor_model=compressor_model, freq=80,
        condenser_model=condenser_model, fan_model=fan_model, ref=ref,
        t0=0, ta=30, sh_0=10, sub=10, rhx=10, ihx=10, sh_ihx=10,
        Q_sub=10, Q_rhx=10, Q_ihx=10, mode=mode, declared_points=None
    )

    if should_raise:
        with pytest.raises(exc_type):
            sim.validate_input()
    else:
        sim.validate_input()

def sample_size_finite(N, Z=1.96, p=0.5, E=0.05):
    """
    Calculate sample size for a finite population.
    
    N: population size
    Z: Z-score (e.g. 1.96 for 95% confidence)
    p: expected proportion (use 0.5 if unknown)
    E: margin of error (e.g. 0.05 for ±5%)
    """
    numerator = N * Z**2 * p * (1 - p)
    denominator = (E**2 * (N - 1)) + (Z**2 * p * (1 - p))
    n = numerator / denominator
    return math.ceil(n)


# test one config of the refrigeration system
@pytest.fixture
def fixed_params():
    return {'data_source': 'components_data.xlsx',
            'compressor_model': 'Compressor_B',
            'freq': 80,
            'condenser_model': 'Condenser_A',
            'fan_model': 'Fan_A',
            'ref': 'R404A',
            'mode': ["inverter", "MT"]}

def param_temp(limits=(0, 30)):
    param_names = ['sh_0', 'sub', 'rhx', 'ihx', 'sh_ihx', 'Q_sub', 'Q_rhx', 'Q_ihx']
    values = [-10, 0, 10, 50]

    combinations = list(itertools.product(values, repeat=len(param_names)))
    df = pd.DataFrame(combinations, columns=param_names)
    n_finite = sample_size_finite(N=df.shape[0])

    df_sample = df.sample(n_finite*5)
    df_sample['should_raise'] = False
    df_sample['exc_type'] = None

    # temperature-related parameters
    cols_temp = ['sh_0', 'sub', 'rhx', 'ihx', 'sh_ihx']
    mask_temp = ((df_sample[cols_temp] < limits[0]) | (df_sample[cols_temp] > limits[1])).any(axis=1)
    df_sample.loc[mask_temp, ['should_raise', 'exc_type']] = [True, ValueError]

    # if temp difference in HEX = 0 then capacity = 0
    temp_HEX = param_names[1:4]
    cap_HEX = param_names[5:8]
    
    for t, Q in zip(temp_HEX, cap_HEX):
        df_sample.loc[df_sample[t] == 0, Q] = 0
        
    # capacity-related parameters
    cols_cap = ['Q_sub', 'Q_rhx', 'Q_ihx']
    mask_cap = (df_sample[cols_cap] < limits[0]).any(axis=1)
    df_sample.loc[mask_cap, ['should_raise', 'exc_type']] = [True, ValueError]    

    return list(df_sample.itertuples(index=False, name=None))

@pytest.mark.parametrize("sh_0, sub, rhx, ihx, sh_ihx, Q_sub, Q_rhx, Q_ihx, should_raise, exc_type", argvalues=param_temp())
def test_input_validation_for_out_of_range(mock_excel, sh_0, sub, rhx, ihx, sh_ihx,
                                         Q_sub, Q_rhx, Q_ihx, should_raise, exc_type, fixed_params):
    sim = RefrigerationSimulator(
        run_simulation=False,
        run_SEPR_calculation=False,
        mode_use_declared=False,
        show_report=False,
        data_source=fixed_params['data_source'],
        compressor_model=fixed_params['compressor_model'],
        freq=fixed_params['freq'],
        condenser_model=fixed_params['condenser_model'],
        fan_model=fixed_params['fan_model'],
        ref=fixed_params['ref'],
        t0=None,
        ta=None,
        sh_0=sh_0, sub=sub, rhx=rhx, ihx=ihx, sh_ihx=sh_ihx,
        Q_sub=Q_sub, Q_rhx=Q_rhx, Q_ihx=Q_ihx,
        mode=fixed_params['mode'],
        declared_points=None
    )

    if should_raise:
        with pytest.raises(exc_type):
            sim.validate_input()
    else:
        sim.validate_input()   
        
@pytest.mark.parametrize('sub, rhx, ihx, Q_sub, Q_rhx, Q_ihx, exp_Q_sub, exp_Q_rhx, exp_Q_ihx',[
    (0, 5, 5, 10, 10, 10, 0, 10, 10),
    (5, 0, 5, 10, 10, 10, 10, 0, 10),
    (5, 5, 0, 10, 10, 10, 10, 10, 0)
    ])
def test_input_validation_for_HEX(mock_excel, sub, rhx, ihx, Q_sub, Q_rhx, Q_ihx, exp_Q_sub, exp_Q_rhx, exp_Q_ihx, fixed_params):
    sim = RefrigerationSimulator(
        run_simulation=False,
        run_SEPR_calculation=False,
        mode_use_declared=False,
        show_report=False,
        data_source=fixed_params['data_source'],
        compressor_model=fixed_params['compressor_model'],
        freq=fixed_params['freq'],
        condenser_model=fixed_params['condenser_model'],
        fan_model=fixed_params['fan_model'],
        ref=fixed_params['ref'],
        t0=None,
        ta=None,
        sh_0=5, sub=sub, rhx=rhx, ihx=ihx, sh_ihx=5,
        Q_sub=Q_sub, Q_rhx=Q_rhx, Q_ihx=Q_ihx,
        mode=fixed_params['mode'],
        declared_points=None
    )
    
    sim.validate_input()

    assert (sim.Q_sub, sim.Q_rhx, sim.Q_ihx) == (exp_Q_sub, exp_Q_rhx, exp_Q_ihx)

'''
Test refrigeration system simulation
'''
@pytest.fixture
def real_excel_data():
    path = Path("components_data.xlsx")
    if not path.exists():
        pytest.skip(f"Excel file not found: {path.resolve()}")
    return str(path.resolve())

# Test two configs of the refrigeration system
@pytest.fixture(
    params=[
        ('Compressor_B', 80, 'Condenser_A', 'Fan_A', "R404A", ["inverter", "MT"]),
        ('Compressor_A', 80, 'Condenser_B', 'Fan_B', "R134a", ["inverter", "MT"])
    ]
)
def units_config(request):
    compressor_model, freq, condenser_model, fan_model, ref, mode = request.param
    return {
        'compressor_model': compressor_model,
        'freq': freq,
        'condenser_model': condenser_model,
        'fan_model': fan_model,
        'ref': ref,
        'mode': mode
    }

def param_sim():
    df_main_temp = pd.DataFrame({
        't0': [-20, -10, 0, 5] *2,
        'ta': [38]*4 + [25]*4,
        'sh_0': [5, 10] * 4,
        })
    
    df_add_hex = pd.DataFrame({
        'sub':      [3,	  3,	   3,	3,	 0,	0,	 0,	  0],
        'rhx':      [0,	  3,	   0,	3,	 0,	3,	 0,	  3],
        'ihx':      [0,	  0,	   3,	3,	 0,	0,	 3,	  3],
        'Q_sub':    [0.2	, 0.2, 0.2, 0.2, 0, 	0,	 0,	  0],
        'Q_rhx':    [0,	  0.3, 0, 	0.3, 0,	0.3,	 0,	  0.3],
        'Q_ihx':    [0,	  0,   0.5,	0.5,	 0,	0,	 0.5, 0.5],
        'sh_ihx':   [0,	  0,   5,	5,	 0,	0,	 5,   5] 
        })
    
    df = pd.merge(df_main_temp, df_add_hex, how='cross')
    
    df['should_raise'] = False
    df['exc_type'] = None

    return list(df.itertuples(index=False, name=None))

@pytest.mark.parametrize("t0, ta, sh_0, sub, rhx, ihx, Q_sub, Q_rhx, Q_ihx, sh_ihx, should_raise, exc_type", argvalues=param_sim())
def test_simulation(t0, ta, sh_0, sub, rhx, ihx, Q_sub, Q_rhx, Q_ihx, sh_ihx, should_raise, exc_type, real_excel_data, units_config):
    sim = RefrigerationSimulator(
        run_simulation=True,
        run_SEPR_calculation=False,
        mode_use_declared=False,
        show_report=False,
        data_source=real_excel_data,
        compressor_model=units_config['compressor_model'],
        freq=units_config['freq'],
        condenser_model=units_config['condenser_model'],
        fan_model=units_config['fan_model'],
        ref=units_config['ref'],
        t0=t0,
        ta=ta,
        sh_0=sh_0, sub=sub, rhx=rhx, ihx=ihx, sh_ihx=sh_ihx,
        Q_sub=Q_sub, Q_rhx=Q_rhx, Q_ihx=Q_ihx,
        mode=units_config['mode'],
        declared_points=None
    )
    
    if units_config['ref'].lower() == "r134a" and t0 == -20 and rhx > 0:
        should_raise = True
        exc_type = ValueError
        
    if should_raise:
        with pytest.raises(exc_type):
            sim.run_simulator()
    else:
        sim.run_simulator() 

'''
Test SEPR calculation
'''
# Test three configs of the refrigeration system
@pytest.mark.parametrize('compressor_model, freq, condenser_model, fan_model, ref, mode',[
    ('Compressor_B', 80, 'Condenser_A', 'Fan_A', "R404A", ["inverter", "MT"]),
    ('Compressor_B', 80, 'Condenser_A', 'Fan_A', "R404A", ["inverter", "LT"]),
    ('Compressor_A', 80, 'Condenser_B', 'Fan_B', "R134a", ["inverter", "MT"])
    ])

def test_sepr_calculation(real_excel_data, compressor_model, freq, condenser_model, fan_model, ref, mode):
    sim = RefrigerationSimulator(
        run_simulation=False,
        run_SEPR_calculation=True,
        mode_use_declared=False,
        show_report=False,
        data_source=real_excel_data,
        compressor_model=compressor_model,
        freq=freq,
        condenser_model=condenser_model,
        fan_model=fan_model,
        ref=ref,
        t0=0,
        ta=30,
        sh_0=5, sub=5, rhx=0, ihx=0, sh_ihx=5,
        Q_sub= 0.2, Q_rhx=0, Q_ihx=0,
        mode=mode,
        declared_points= [None]*8
    )
    
    try:
        sim.run_simulator()
    except Exception:
        pytest.fail("Refrigeration Simulator raised an unexpected exception")

