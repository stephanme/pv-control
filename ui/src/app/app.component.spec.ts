import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ReactiveFormsModule } from '@angular/forms';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { By } from '@angular/platform-browser';

import { MatToolbar } from '@angular/material/toolbar';
import { MatCard, MatCardContent, MatCardHeader, MatCardTitle } from '@angular/material/card';
import { MatIcon } from '@angular/material/icon';
import { MatIconButton } from '@angular/material/button';
import { MatButtonToggle, MatButtonToggleGroup } from '@angular/material/button-toggle';

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HarnessLoader } from '@angular/cdk/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { MatButtonHarness } from '@angular/material/button/testing';
import { MatButtonToggleHarness } from '@angular/material/button-toggle/testing';
import { MatSnackBarHarness } from '@angular/material/snack-bar/testing';

import { AppComponent } from './app.component';
import { ChargeMode, PhaseMode, Priority, PvControl } from './pv-control.service';
import { statusInterceptor } from './http-status.service';
import { provideExperimentalZonelessChangeDetection } from '@angular/core';


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
  let priorityAuto: MatButtonToggleHarness;
  let priorityHomeBattery: MatButtonToggleHarness;
  let priorityCar: MatButtonToggleHarness;
  let refreshButton: MatButtonHarness;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        BrowserAnimationsModule,
        ReactiveFormsModule,
        MatCard,
        MatCardContent,
        MatCardHeader,
        MatCardTitle,
        MatIcon,
        MatIconButton,
        MatButtonToggle,
        MatButtonToggleGroup,
        MatToolbar,
        AppComponent
      ],
      providers: [
        provideExperimentalZonelessChangeDetection(),
        provideHttpClient(withInterceptors([statusInterceptor])),
        provideHttpClientTesting(),
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
        power_grid: -1500,
        power_battery: -500,
        soc_battery: 50,
      },
      wallbox: {
        error: 0,
        car_status: 2,
        allow_charging: true,
        max_current: 8,
        phases_in: 3,
        phases_out: 3,
        power: 2000,
        temperature: 10.3,
      },
      controller: {
        error: 0,
        mode: ChargeMode.OFF,
        desired_mode: ChargeMode.OFF,
        phase_mode: PhaseMode.AUTO,
        priority: Priority.HOME_BATTERY,
        desired_priority: Priority.AUTO,
      },
      car: {
        error: 0,
        soc: 50,
        cruising_range: 150,
      }
    };

    jasmine.clock().install();
    // wait for ngInit
    await fixture.whenStable();
    // pass initial 200ms wait for first refresh
    jasmine.clock().tick(300);

    chargeModeOff = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModeOFF' }));
    chargeModeMax = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModeMAX' }));
    chargeModePvOnly = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#chargeModePV_ONLY' }));
    phaseModeAuto = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#phaseModeAUTO' }));
    phaseModeCharge1P = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#phaseModeCHARGE_1P' }));
    priorityAuto = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#priorityAUTO' }));
    priorityHomeBattery = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#priorityHOME_BATTERY' }));
    priorityCar = await loader.getHarness(MatButtonToggleHarness.with({ selector: '#priorityCAR' }));
    refreshButton = await loader.getHarness(MatButtonHarness.with({ selector: '#refresh' }));
  });

  afterEach(() => {
    jasmine.clock().uninstall();
    httpMock.verify();
  });

  it('should render the app', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.chargeModeControl.value).toBe(ChargeMode.OFF);
    expect(await chargeModeOff.isChecked()).toBeTrue();
    expect(component.phaseModeControl.value).toBe(PhaseMode.AUTO);
    expect(await phaseModeAuto.isChecked()).toBeTrue();
    expect(component.priorityControl.value).toBe(Priority.AUTO);
    expect(await priorityAuto.isChecked()).toBeTrue();

    expect(fixture.debugElement.query(By.css('#card-pv span')).nativeElement.textContent).toContain('5.0 kW');
    expect(fixture.debugElement.query(By.css('#card-grid span')).nativeElement.textContent).toContain('-1.5 kW');
    expect(fixture.debugElement.query(By.css('#card-grid mat-icon')).nativeElement.className).toContain('col-green');
    expect(fixture.debugElement.query(By.css('#card-home span')).nativeElement.textContent).toContain('1.0 kW');
    expect(fixture.debugElement.query(By.css('#card-battery span')).nativeElement.textContent).toContain('-0.5 kW');
    expect(fixture.debugElement.query(By.css('#card-battery mat-icon')).nativeElement.textContent).toContain('battery_charging_60');
    expect(fixture.debugElement.query(By.css('#card-car span')).nativeElement.textContent).toContain('50 %');
    expect(fixture.debugElement.query(By.css('#card-temp span')).nativeElement.textContent).toContain('10 °C');

    expect(fixture.debugElement.query(By.css('#car-max-current')).nativeElement.textContent).toContain('3x 8 A');
    expect(fixture.debugElement.query(By.css('#car-charge-power')).nativeElement.textContent).toContain('2.0 kW');
    expect(fixture.debugElement.query(By.css('#car-charge-state'))).toBeNull();
  });

  it('should render car status', async () => {
    pvControlData.wallbox.car_status = 1;
    pvControlData.wallbox.phases_out = 0;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(fixture.debugElement.query(By.css('#car-max-current'))).toBeNull();
    expect(fixture.debugElement.query(By.css('#car-charge-power'))).toBeNull();
    expect(fixture.debugElement.query(By.css('#car-charge-state')).nativeElement.textContent).toContain('power_off');
  });

  it('should refresh data', async () => {
    const refreshIcon = fixture.debugElement.query(By.css('#refresh mat-icon')).nativeElement;

    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
    await fixture.whenStable();

    expect(refreshIcon.className).not.toContain('spin');
    expect(component.chargeModeControl.value).toBe(ChargeMode.OFF);

    pvControlData.controller.mode = ChargeMode.PV_ONLY;
    pvControlData.controller.desired_mode = ChargeMode.PV_ONLY;
    pvControlData.controller.phase_mode = PhaseMode.CHARGE_1P;
    pvControlData.controller.priority = Priority.CAR;
    pvControlData.controller.desired_priority = Priority.CAR;
    await refreshButton.click();

    expect(refreshIcon.className).toContain('spin');
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.chargeModeControl.value).toBe(ChargeMode.PV_ONLY);
    expect(component.phaseModeControl.enabled).toBeTrue();
    expect(component.phaseModeControl.value).toBe(PhaseMode.CHARGE_1P);
    expect(component.priorityControl.value).toBe(Priority.CAR);
    expect(await chargeModePvOnly.isChecked()).toBeTrue();
    expect(await phaseModeCharge1P.isChecked()).toBeTrue();
    expect(await priorityCar.isChecked()).toBeTrue();
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

  it('should show grey icons on sub system error', async () => {
    pvControlData.meter.error = 4;
    pvControlData.car.error = 4;
    pvControlData.wallbox.error = 4;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
    await fixture.whenStable();

    expect(fixture.debugElement.query(By.css('#card-pv mat-icon')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-pv span')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-grid mat-icon')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-grid span')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-home mat-icon')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-home span')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-battery span')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-battery mat-icon')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-car mat-icon')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-car span')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-chargemode mat-icon')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-chargemode span')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-temp mat-icon')).nativeElement.className).toContain('col-grey');
    expect(fixture.debugElement.query(By.css('#card-temp span')).nativeElement.className).toContain('col-grey');
  });

  it('should allow to switch to "PV only" charging', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

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

    expect(await chargeModeOff.isChecked()).toBeTrue();
  });

  it('should show Max in MANUAL mode', async () => {
    pvControlData.controller.desired_mode = ChargeMode.MANUAL;
    pvControlData.controller.mode = ChargeMode.MAX;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(await chargeModeMax.isChecked()).toBeTrue();
  });

  it('should allow to switch to "1 phase" charging', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    await phaseModeCharge1P.check();

    const req = httpMock.expectOne('./api/pvcontrol/controller/phase_mode');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe('"CHARGE_1P"');
    req.flush(null);

    expect(await phaseModeCharge1P.isChecked()).toBeTrue();
    expect(await phaseModeAuto.isChecked()).toBeFalse();
  });

  it('should support disabled phase relay', async () => {
    pvControlData.controller.phase_mode = PhaseMode.DISABLED;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
    await fixture.whenStable();

    expect(component.phaseModeControl.disabled).toBeTrue();
    expect(await phaseModeAuto.isChecked()).toBeFalse();
    expect(await phaseModeAuto.isDisabled()).toBeTrue();
  });

  it('should allow to switch to charging priority CAR', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    await priorityCar.check();

    const req = httpMock.expectOne('./api/pvcontrol/controller/priority');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe('"CAR"');
    req.flush(null);

    expect(await priorityCar.isChecked()).toBeTrue();
    expect(await priorityAuto.isChecked()).toBeFalse();
  });
});

describe('AppComponent', () => {
  const pvControlData: PvControl = {
    meter: {
      error: 0,
      power_pv: 5000,
      power_consumption: 3000,
      power_grid: -1000,
      power_battery: -1000,
      soc_battery: 50,
    },
    wallbox: {
      error: 0,
      car_status: 1,
      allow_charging: false,
      max_current: 8,
      phases_in: 3,
      phases_out: 0,
      power: 0,
      temperature: 0,
    },
    controller: {
      error: 0,
      mode: ChargeMode.OFF,
      desired_mode: ChargeMode.OFF,
      phase_mode: PhaseMode.AUTO,
      priority: Priority.HOME_BATTERY,
      desired_priority: Priority.AUTO,
    },
    car: {
      error: 0,
      soc: 50,
      cruising_range: 150,
    }
  };

  it('should support wallboxChargingIcon()', () => {
    pvControlData.wallbox.phases_out = 0;
    pvControlData.wallbox.car_status = 0; // unknown
    expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('battery_unknown');

    pvControlData.wallbox.car_status = 1; // NoVehicle
    expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('power_off');
    pvControlData.wallbox.car_status = 2; // Charging
    expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('battery_charging_50');
    pvControlData.wallbox.car_status = 3; // WaitingForVehicle
    expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('hourglass_bottom');

    pvControlData.wallbox.car_status = 4; // ChargingFinished
    pvControlData.wallbox.allow_charging = false;
    expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('battery_3_bar');
    pvControlData.wallbox.allow_charging = true;
    expect(AppComponent.wallboxChargingIcon(pvControlData)).toBe('battery_full');
  });

  it('should support batteryIcon()', () => {
    pvControlData.meter.power_battery = -1000;
    pvControlData.meter.soc_battery = 0;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_charging_20');
    pvControlData.meter.soc_battery = 50;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_charging_60');
    pvControlData.meter.soc_battery = 99;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_charging_full');
    pvControlData.meter.soc_battery = 100;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_charging_full');

    pvControlData.meter.power_battery = 1000;
    pvControlData.meter.soc_battery = 0;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_0_bar');
    pvControlData.meter.soc_battery = 50;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_4_bar');
    pvControlData.meter.soc_battery = 90;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_6_bar');
    pvControlData.meter.soc_battery = 99;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_full');
    pvControlData.meter.soc_battery = 100;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_full');

    pvControlData.meter.power_battery = 0;
    expect(AppComponent.batteryIcon(pvControlData)).toBe('battery_full');
  });
});
