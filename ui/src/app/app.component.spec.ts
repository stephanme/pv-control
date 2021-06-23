import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ReactiveFormsModule } from '@angular/forms';
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import { By } from '@angular/platform-browser';

import { MatToolbarModule } from '@angular/material/toolbar';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { HarnessLoader } from '@angular/cdk/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { MatButtonHarness } from '@angular/material/button/testing';
import { MatButtonToggleHarness } from '@angular/material/button-toggle/testing';
import { MatSnackBarHarness } from '@angular/material/snack-bar/testing';
import { FlexLayoutModule } from '@angular/flex-layout';

import { AppComponent } from './app.component';
import { ChargeMode, PhaseMode, PvControl } from './pv-control.service';
import { HttpStatusInterceptor } from './http-status.service';


describe('AppComponent', () => {
  let loader: HarnessLoader;
  let httpMock: HttpTestingController;
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;
  let pvControlData: PvControl;
  let chargeModeOff: MatButtonToggleHarness;
  let chargeModePvOnly: MatButtonToggleHarness;
  let chargeModeMax: MatButtonToggleHarness;
  let phaseModeAuto: MatButtonToggleHarness;
  let phaseModeCharge1P: MatButtonToggleHarness;
  let refreshButton: MatButtonHarness;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        BrowserAnimationsModule,
        HttpClientTestingModule,
        ReactiveFormsModule,
        FlexLayoutModule,
        MatToolbarModule,
        MatCardModule,
        MatFormFieldModule,
        MatInputModule,
        MatIconModule,
        MatButtonModule,
        MatButtonToggleModule,
        MatSlideToggleModule,
        MatSnackBarModule,
      ],
      declarations: [
        AppComponent
      ],
      providers: [
        {
          provide: HTTP_INTERCEPTORS,
          useClass: HttpStatusInterceptor,
          multi: true,
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    loader = TestbedHarnessEnvironment.loader(fixture);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);

    pvControlData = {
      meter: {
        error: 0,
        power_pv: 5000,
        power_consumption: 3000,
        power_grid: -2000
      },
      wallbox: {
        error: 0,
        car_status: 2,
        allow_charging: true,
        max_current: 8,
        phases_in: 3,
        phases_out: 3,
        power: 2000,
      },
      controller: {
        error: 0,
        mode: ChargeMode.OFF,
        desired_mode: ChargeMode.OFF,
        phase_mode: PhaseMode.AUTO,
      },
      car: {
        error: 0,
        soc: 50,
        cruising_range: 150,
      }
    };

    chargeModeOff = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModeOFF' }));
    chargeModeMax = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModeMAX' }));
    chargeModePvOnly = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModePV_ONLY' }));
    phaseModeAuto = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#phaseModeAUTO' }));
    phaseModeCharge1P = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#phaseModeCHARGE_1P' }));
    refreshButton = await loader.getHarness(MatButtonHarness.with({ selector: '#refresh' }));
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should render the app', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(component.chargeModeControl.value).toBe(ChargeMode.OFF);
    expect(await chargeModeOff.isChecked()).toBeTrue();
    expect(component.phaseModeControl.value).toBe(PhaseMode.AUTO);
    expect(await phaseModeAuto.isChecked()).toBeTrue();

    expect(fixture.debugElement.query(By.css('#card-pv span')).nativeElement.textContent).toContain('5.0 kW');
    expect(fixture.debugElement.query(By.css('#card-grid span')).nativeElement.textContent).toContain('-2.0 kW');
    expect(fixture.debugElement.query(By.css('#card-grid mat-icon')).nativeElement.className).toContain('col-green');
    expect(fixture.debugElement.query(By.css('#card-home span')).nativeElement.textContent).toContain('1.0 kW');
    expect(fixture.debugElement.query(By.css('#card-car span')).nativeElement.textContent).toContain('50 %');

    expect(fixture.debugElement.query(By.css('#car-max-current')).nativeElement.textContent).toContain('3x 8 A');
    expect(fixture.debugElement.query(By.css('#car-charge-power')).nativeElement.textContent).toContain('2.0 kW');
    expect(fixture.debugElement.query(By.css('#car-charge-state'))).toBeNull();
  });

  it('should render car status', async () => {
    pvControlData.wallbox.car_status = 1;
    pvControlData.wallbox.phases_out = 0;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('#car-max-current'))).toBeNull();
    expect(fixture.debugElement.query(By.css('#car-charge-power'))).toBeNull();
    expect(fixture.debugElement.query(By.css('#car-charge-state')).nativeElement.textContent).toContain('power_off');
  });


  it('should refresh data', async () => {
    const refreshIcon = fixture.debugElement.query(By.css('#refresh mat-icon')).nativeElement;

    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
    fixture.detectChanges();

    expect(refreshIcon.className).not.toContain('spin');
    expect(component.pvControl).toEqual(pvControlData);
    expect(component.chargeModeControl.value).toBe(ChargeMode.OFF);

    pvControlData.controller.mode = ChargeMode.PV_ONLY;
    pvControlData.controller.desired_mode = ChargeMode.PV_ONLY;
    pvControlData.controller.phase_mode = PhaseMode.CHARGE_1P;
    await refreshButton.click();

    expect(refreshIcon.className).toContain('spin');
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(component.chargeModeControl.value).toBe(ChargeMode.PV_ONLY);
    expect(component.phaseModeControl.value).toBe(PhaseMode.CHARGE_1P);
    expect(await chargeModePvOnly.isChecked()).toBeTrue();
    expect(await phaseModeCharge1P.isChecked()).toBeTrue();
    expect(refreshIcon.className).not.toContain('spin');
  });

  it('should show an error msg on http problems', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    await refreshButton.click();
    httpMock.expectOne('./api/pvcontrol').flush('', {
      status: 500,
      statusText: 'Internal Server Error'
    });

    // snack bar is not below root element of fixture -> can't use loader
    const snackbar = await TestbedHarnessEnvironment.documentRootLoader(fixture).getHarness(MatSnackBarHarness);
    expect(await snackbar.getMessage()).toBe('HTTP 500 Internal Server Error - GET ./api/pvcontrol');
  });

  it('should allow to switch to "PV only" charging', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    await chargeModePvOnly.check();

    const req = httpMock.expectOne('./api/pvcontrol/controller/desired_mode');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe('"PV_ONLY"');
    req.flush(null);

    expect(await chargeModePvOnly.isChecked()).toBeTrue();
    expect(await chargeModeOff.isChecked()).toBeFalse();
  });

  it('should show Off in MANUAL mode', async () => {
    pvControlData.controller.desired_mode = ChargeMode.MANUAL;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(await chargeModeOff.isChecked()).toBeTrue();
  });

  it('should show Max in MANUAL mode', async () => {
    pvControlData.controller.desired_mode = ChargeMode.MANUAL;
    pvControlData.controller.mode = ChargeMode.MAX;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(await chargeModeMax.isChecked()).toBeTrue();
  });

  it('should allow to switch to "1 phase" charging', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    await phaseModeCharge1P.check();

    const req = httpMock.expectOne('./api/pvcontrol/controller/phase_mode');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe('"CHARGE_1P"');
    req.flush(null);

    expect(await phaseModeCharge1P.isChecked()).toBeTrue();
    expect(await phaseModeAuto.isChecked()).toBeFalse();
  });
});

describe('AppComponent', () => {
  const pvControlData = {
    meter: {
      error: 0,
      power_pv: 5000,
      power_consumption: 3000,
      power_grid: -2000
    },
    wallbox: {
      error: 0,
      car_status: 1,
      allow_charging: false,
      max_current: 8,
      phases_in: 3,
      phases_out: 0,
      power: 0,
    },
    controller: {
      error: 0,
      mode: ChargeMode.OFF,
      desired_mode: ChargeMode.OFF,
      phase_mode: PhaseMode.AUTO,
    },
    car: {
      error: 0,
      soc: 50,
      cruising_range: 150,
    }
  };

  it('should support isCharging()', () => {
    pvControlData.wallbox.phases_out = 0;
    expect(AppComponent.isCharging(pvControlData)).toBeFalse();
    pvControlData.wallbox.phases_out = 1;
    expect(AppComponent.isCharging(pvControlData)).toBeTrue();
    pvControlData.wallbox.phases_out = 3;
    expect(AppComponent.isCharging(pvControlData)).toBeTrue();
  });

  it('should support chargingStateIcon()', () => {
    pvControlData.wallbox.phases_out = 0;
    pvControlData.wallbox.car_status = 0; // unknown
    expect(AppComponent.chargingStateIcon(pvControlData)).toBe('battery_unknown');

    pvControlData.wallbox.car_status = 1; // NoVehicle
    expect(AppComponent.chargingStateIcon(pvControlData)).toBe('power_off');
    pvControlData.wallbox.car_status = 2; // Charging
    expect(AppComponent.chargingStateIcon(pvControlData)).toBe('battery_charging_full');
    pvControlData.wallbox.car_status = 3; // WaitingForVehicle
    expect(AppComponent.chargingStateIcon(pvControlData)).toBe('hourglass_empty');

    pvControlData.wallbox.car_status = 4; // ChargingFinished
    pvControlData.wallbox.allow_charging = false;
    expect(AppComponent.chargingStateIcon(pvControlData)).toBe('battery_saver');
    pvControlData.wallbox.allow_charging = true;
    expect(AppComponent.chargingStateIcon(pvControlData)).toBe('battery_full');
  });
});
